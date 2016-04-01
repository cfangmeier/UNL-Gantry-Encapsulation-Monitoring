#!/usr/bin/env python3
import io
import re
import sys
import json
import zipfile
import collections

Vec3d = collections.namedtuple("Vec3d", "x,y,z")
Orient3d = collections.namedtuple("Orient3d", "x,y,z,q")


def load_logfiles(full_zipfile_name):
    fullzf = zipfile.ZipFile(full_zipfile_name)
    logs = []
    for zip_member in fullzf.filelist:
        zip_fname = zip_member.filename
        # Extract inner zipfile
        with fullzf.open(zip_fname) as f:
            b = io.BytesIO(f.read())
        # Open extracted zipfile and read Potting.log into memory
        zf = zipfile.ZipFile(b)
        with zf.open("Potting.log") as f:
            log = f.read().decode('utf8')
            logs.append((zip_fname, log))
    return logs


def split_sections(log):
    sec_re = re.compile(("(Configure Tester|Inspect Fiducials|"
                         "Review Fiducials|Inspect Modules|"
                         "Review Modules|Load Sylgard|"
                         "Align Needle|Purge|Pot|Finish) started"))
    sections = {}
    sec_curr_name = None
    sec_curr_lines = None
    for line in log.split('\n'):
        res = sec_re.findall(line)
        if res:
            if sec_curr_name:
                sections[sec_curr_name] = sec_curr_lines
            sec_curr_name = res[0]
            sec_curr_lines = []
        elif sec_curr_name:
            sec_curr_lines.append(line)
    return sections


def parse_modules(log):
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
                                          'pot_lines': {}}
        return modules

    def parse_alignment(lines, modules):
        reg_fid = re.compile(("Chuck (\d+) Slot (\d+): , "
                              "(BBM|HDI) Fiducial (.*): Source: (.*), "
                              "Image Position: ([\d.]*),([\d.]*),([\d.]*), "
                              "Image Coordinate: ([\d.]*),([\d.]*),([\d.]*), "
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
    secs = split_sections(log)
    modules = parse_tablestate(secs['Configure Tester'])
    parse_alignment(secs['Review Fiducials'], modules)
    parse_lines(secs['Pot'], modules)
    return list(modules.values())


def main(full_zipfile_name):
    logs = load_logfiles(full_zipfile_name)
    modules = []
    for filename, log in logs:
        try:
            mods = parse_modules(log)
            print("parsed {} modules from {}".format(len(mods), filename))
            modules += mods
        except KeyError:
            print("file: {} Has invalid format, skipping...".format(filename))

    enc = json.JSONEncoder()
    with open('Potting_Logs.json', 'w') as f:
        f.write(enc.encode(modules))

if __name__ == '__main__':
    try:
        fname = sys.argv[1]
        main(fname)
    except IndexError:
        print("Usage: ./PottingLog2JSON PottingLogs.zip")
