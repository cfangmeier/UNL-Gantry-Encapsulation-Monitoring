#!/usr/bin/env python3
import io
import re
import sys
import json
import zipfile
import collections
import openpyxl

Vec3d = collections.namedtuple("Vec3d", "x,y,z")
Orient3d = collections.namedtuple("Orient3d", "x,y,z,q")


def load_gluing_logs():
    pass


def load_potting_logs(full_zipfile_name):
    fullzf = zipfile.ZipFile(full_zipfile_name)
    fname_re = re.compile('Config-(.*).zip')
    date_re = re.compile('(\d{4})_(\d{2})_(\d{2})-(\d{2})_(\d{2})')
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
            dt = [int(m) for m in date_re.findall(zip_fname)[0]]
            dt = {'year': dt[0], 'month': dt[1],
                  'day': dt[2], 'hour': dt[3],
                  'minute': dt[4]}
            logs[short_fname] = (short_fname, dt, log)
    return list(logs.values())


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


def parse_modules(log, dt):
    def parse_time_taken():
        from datetime import datetime
        fmt = '%d/%m/%Y %H:%M:%S %p'
        ts = log[0].split('>>>')[0].strip()
        ts = datetime.strptime(ts, fmt)
        tf = log[-2].split('>>>')[0].strip()
        tf = datetime.strptime(tf, fmt)
        return (tf-ts).seconds // 60

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
                modules[(chuck, slot)] = {'id': id_,
                                          'chuck': chuck,
                                          'slot': slot,
                                          'HDI_fids': {},
                                          'BBM_fids': {},
                                          'pot_lines': {},
                                          'date_potted': dt}
        return modules

    def parse_alignment(lines, modules):
        reg_fid = re.compile(("Chuck (\d+) Slot (\d+): , "
                              "(BBM|HDI) Fiducial (.*): Source: (.*), "
                              "Image Position: ([\d.]*),([\d.]*),([\d.]*), "
                              "Image Coor?dinate: ([\d.]*),([\d.]*),([\d.]*), "
                              "Fiducial Position: ([\d.]*),([\d.]*),([\d.]*)"))
        reg_mod = re.compile(("Chuck (\d+) Slot (\d+): , (BBM|HDI) "
                              "Center:([\d.]*),([\d.]*),([\d.]*) "
                              "Orientation:([\d.-]*),([\d.-]*),"
                              "([\d.-]*),([\d.-]*) "
                              "Rotation:([\d.-]*) degrees"))
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
                mod[res[2]+"_fids"][res[3]] = fid
            res_mod = reg_mod.findall(line)
            if res_mod:
                res = res_mod[0]
                mod = modules[(res[0], res[1])]
                mod[res[2]+'_center'] = Vec3d(*res[3:6])
                mod[res[2]+'_orient'] = Orient3d(*res[6:10])
                mod[res[2]+'_rotatn'] = res[10]

    def parse_lines(lines, modules):
        reg = re.compile(("Chuck (\d+) Slot (\d+): : (.*), "
                          "Global: ([\d.-]*),([\d.-]*),([\d.-]*)->"
                          "([\d.-]*),([\d.-]*),([\d.-]*), "
                          "Local: ([\d.-]*),([\d.-]*),([\d.-]*)->"
                          "([\d.-]*),([\d.-]*),([\d.-]*), "
                          "(Enabled|Disabled)"))
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
    parse_lines(secs['Pot'], modules)
    parse_finish(secs['Finish'], modules)
    time = parse_time_taken()
    return list(modules.values()), time


def main(full_zipfile_name):
    logs = load_potting_logs(full_zipfile_name)
    modules = []
    for filename, dt, log in logs:
        try:
            mods, time = parse_modules(log, dt)
            time //= len(mods)
            for mod in mods:
                mod['time'] = time
                mod['source_file'] = filename
            print("parsed {} modules from {}".format(len(mods), filename))
            modules += mods
        except KeyError:
            print("file: {} Has invalid format, skipping...".format(filename))
            # import traceback
            # print(traceback.format_exc())

    enc = json.JSONEncoder(indent='  ')
    with open('Potting_Logs.json', 'w') as f:
        f.write(enc.encode(modules))

if __name__ == '__main__':
    try:
        fname = sys.argv[1]
        main(fname)
    except IndexError:
        print("Usage: ./PottingLog2JSON PottingLogs.zip")
