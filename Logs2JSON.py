#!/usr/bin/env python3
import io
import re
import json
import pydoc
import zipfile
import traceback
import argparse
import collections
from datetime import datetime
import urllib.request as request
from itertools import count

Vec3d = collections.namedtuple('Vec3d', 'x,y,z')
Orient3d = collections.namedtuple('Orient3d', 'x,y,z,q')


def parse_potting_datetime(pot_log_line):
    dt_str = pot_log_line.split('>>>')[0].strip()
    return datetime.strptime(dt_str, '%d/%m/%Y %I:%M:%S %p')


def parse_gluing_datetime(glue_log_line, just_date=False):
    colon_pos = glue_log_line.find(':')
    dt_str = glue_log_line[colon_pos+1:].strip()
    if just_date:
        return datetime.strptime(dt_str, '%m/%d/%Y')
    else:
        return datetime.strptime(dt_str, '%d/%m/%Y-%H:%M:%S')


def datetime2str(dt, just_date=False):
    if just_date:
        return dt.strftime('%d/%m/%Y')
    else:
        return dt.strftime('%d/%m/%Y-%H:%M:%S')


def hdi2moduleid(hdi_id):
    try:
        url_base = ("http://inky.physics.purdue.edu/cmsfpix/"
                    "/Submission_p/summary/hdi.php?name={}")
        response = request.urlopen(url_base.format(hdi_id))
        data = response.read().decode('utf8')
        return re.findall('M-.-.-..?', data)[0]
    except IndexError:
        return None


def page(s):
    pydoc.pager(str(s))


def load_gluing_logs(zipfile_name):
    zf = zipfile.ZipFile(zipfile_name)
    logs = collections.OrderedDict()
    fnames = [z.filename for z in zf.filelist]
    for fname in sorted(fnames):
        with zf.open(fname) as f:
            log = f.read().decode('utf8').split('\n')
            logs[fname] = (fname, log)
    return list(logs.values())


def parse_gluing_log(log):
    def value(line):
        return line.split(':')[1].strip()

    date = parse_gluing_datetime(log[4], just_date=True)
    date = datetime2str(date, just_date=True)
    start_time = parse_gluing_datetime(log[5])
    start_time = datetime2str(start_time)
    finish_time = parse_gluing_datetime(log[10])
    finish_time = datetime2str(finish_time)
    operator = value(log[6])
    software_version = value(log[7])
    pressure = value(log[11])
    araldite_batch = value(log[12])
    chuck = value(log[18])

    lines = [l.strip() for l in log[22:30]]
    modules = {}
    for i, (bbm_id, hdi_id) in enumerate(zip(lines[:-1:2], lines[1::2])):
        if bbm_id in {'glass', '---'} or hdi_id in {'kapton', '---'}:
            continue
        mod_id = hdi2moduleid(hdi_id)
        module = {'module_id': mod_id,
                  'hdi_id': hdi_id,
                  'bbm_id': bbm_id,
                  'date': date,
                  'start_time': start_time,
                  'finish_time': finish_time,
                  'operator': operator,
                  'software_version': software_version,
                  'pressure': pressure,
                  'araldite_batch': araldite_batch,
                  'chuck': chuck,
                  'slot': i+1,
                  }
        modules[mod_id] = module
    return modules


def load_potting_logs(full_zipfile_name):
    fullzf = zipfile.ZipFile(full_zipfile_name)
    fname_re = re.compile('Config-(.*).zip')
    logs = collections.OrderedDict()
    zip_fnames = [z.filename for z in fullzf.filelist]
    for zip_fname in sorted(zip_fnames):
        short_fname = fname_re.findall(zip_fname)[0]
        # Extract inner zipfile
        with fullzf.open(zip_fname) as f:
            b = io.BytesIO(f.read())
        # Open extracted zipfile and read Potting.log into memory
        zf = zipfile.ZipFile(b)
        with zf.open("Potting.log") as f:
            log = f.read().decode('utf8').split('\n')
            logs[short_fname] = (short_fname, log)
    return list(logs.values())


def parse_potting_log(log):
    time_start = parse_potting_datetime(log[0])
    for i in count(1):  # Read from end of file looking for last timestamp
        try:
            time_finish = parse_potting_datetime(log[-i])
            break
        except ValueError:
            continue
    time_taken = (time_finish - time_start).seconds // 60

    def split_sections(log):
        sec_re = re.compile(('(Configure Tester|Inspect Fiducials|'
                             'Review Fiducials|Inspect Modules|'
                             'Review Modules|Load Sylgard|'
                             'Align Needle|Purge|Pot|Finish) '
                             'has been executed successfully'))
        sections = {}
        sec_curr_lines = []
        for line in log:
            res = sec_re.findall(line)
            if not res:
                sec_curr_lines.append(line)
            else:
                sections[res[0]] = sec_curr_lines
                sec_curr_lines = []
        return sections

    def parse_tablestate(lines):
        modules = {}
        reg = re.compile("Chuck: (\d+), Slot: (\d+), S/N: (.*), State: (.*)$")
        for line in lines:
            res = reg.findall(line.strip())
            if not res:
                continue
            res = res[0]
            if res[3] != "Empty":
                chuck = res[0]
                slot = res[1]
                id_ = res[2]
                ts = datetime2str(time_start)
                tf = datetime2str(time_finish)
                pd = datetime2str(time_start, just_date=True)
                modules[(chuck, slot)] = {'module_id': id_,
                                          'chuck': chuck,
                                          'slot': slot,
                                          'HDI_fids': {},
                                          'BBM_fids': {},
                                          'pot_lines': {},
                                          'time_start': ts,
                                          'time_end': tf,
                                          'time_taken': time_taken,
                                          'date': pd}
        return modules

    def parse_alignment(lines, modules):
        reg_fid = re.compile(('Chuck (\d+) Slot (\d+): , '
                              '(BBM|HDI) Fiducial (.*): Source: (.*), '
                              'Image Position: ([\d.]*),([\d.]*),([\d.]*), '
                              'Image Coor?dinate: ([\d.]*),([\d.]*),([\d.]*), '
                              'Fiducial Position: ([\d.]*),([\d.]*),([\d.]*)'))
        reg_mod = re.compile(('Chuck (\d+) Slot (\d+): , (BBM|HDI) '
                              'Center:([\d.]*),([\d.]*),([\d.]*) '
                              'Orientation:([\d.-]*),([\d.-]*),'
                              '([\d.-]*),([\d.-]*) '
                              'Rotation:([\d.-]*) degrees'))
        for line in lines:
            res_fid = reg_fid.findall(line)
            if res_fid:
                res = res_fid[0]
                mod = modules[(res[0], res[1])]
                fid = {'name': res[3],
                       'source': res[4],
                       'img_pos': Vec3d(*res[5:8]),
                       'img_crd': Vec3d(*res[8:11]),
                       'fid_pos': Vec3d(*res[11:14])}
                mod[res[2]+'_fids'][res[3]] = fid
            res_mod = reg_mod.findall(line)
            if res_mod:
                res = res_mod[0]
                mod = modules[(res[0], res[1])]
                mod[res[2]+'_center'] = Vec3d(*res[3:6])
                mod[res[2]+'_orient'] = Orient3d(*res[6:10])
                mod[res[2]+'_rotatn'] = res[10]

    def parse_potting_lines(lines, modules):
        reg = re.compile(('Chuck (\d+) Slot (\d+): : (.*), '
                          'Global: ([\d.-]*),([\d.-]*),([\d.-]*)->'
                          '([\d.-]*),([\d.-]*),([\d.-]*), '
                          'Local: ([\d.-]*),([\d.-]*),([\d.-]*)->'
                          '([\d.-]*),([\d.-]*),([\d.-]*), '
                          '(Enabled|Disabled)'))
        for line in lines:
            res = reg.findall(line)
            if res:
                res = res[0]
                mod = modules[(res[0], res[1])]
                line = {'global': {'start': Vec3d(*res[3:6]),
                                   'end': Vec3d(*res[6:9])},
                        'local': {'start': Vec3d(*res[9:12]),
                                  'end': Vec3d(*res[12:15])},
                        'state': res[15]}

                mod['pot_lines'][res[2]] = line

    def parse_finish(lines, modules):
        reg = re.compile('(Operator Name|Sylgard Batch|Pressure):(.*$)')
        for line in lines:
            res = reg.findall(line)
            if res:
                res = res[0]
                for module in modules.values():
                    key = res[0].lower().replace(" ", "_")
                    module[key] = res[1].strip()

    secs = split_sections(log)
    modules = parse_tablestate(secs['Configure Tester'])
    parse_alignment(secs['Review Fiducials'], modules)
    parse_potting_lines(secs['Pot'], modules)
    parse_finish(secs['Finish'], modules)
    time = (time_finish-time_start).seconds // 60
    return list(modules.values()), time


def process_potting_logs(full_zipfile_name):
    logs = load_potting_logs(full_zipfile_name)
    modules = []
    for filename, log in logs:
        try:
            mods, time = parse_potting_log(log)
            time //= len(mods)
            for mod in mods:
                mod['time'] = time
                mod['source_file'] = filename
            print("parsed {} modules from {}".format(len(mods), filename))
            modules += mods
        except KeyError as e:
            print("file: {} Has invalid format, skipping...".format(filename))
            traceback.print_exc()
            print(e)
    return modules


def process_gluing_logs(zipfile_name):
    logs = load_gluing_logs(zipfile_name)
    modules = {}
    for log_file, log in logs[-5:]:
        modules.update(parse_gluing_log(log))
    return modules.values()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=('Convert manufacturing '
                                                  'log files to json'))
    arg = parser.add_argument
    arg('--pottinglog', help='Zipfile containing Potting log files')
    arg('--gluinglog', help='Zipfile containing Gluing log files')
    args = parser.parse_args()
    pot_logs = {}
    glue_logs = {}
    if args.pottinglog is not None:
        pot_logs = process_potting_logs(args.pottinglog)
    if args.gluinglog is not None:
        glue_logs = process_gluing_logs(args.gluinglog)

    logs = collections.defaultdict(dict)
    for log in pot_logs:
        mod_id = log.pop('module_id').upper()
        logs[mod_id]['potting'] = log
    for log in glue_logs:
        if log['module_id'] is None:
            continue
        mod_id = log.pop('module_id').upper()
        logs[mod_id]['gluing'] = log

    enc = json.JSONEncoder(indent='  ')
    with open('Potting_Logs.json', 'w') as f:
        f.write(enc.encode(logs))
