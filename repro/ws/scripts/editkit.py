import glob
import json
import os

DIR = "edit"


def _path(case, name):
    return os.path.join(case, DIR, name)


def parts_selection(case, act):
    return _path(case, "Edit-Parts-%s.json" % act)


def parts_disabled(case):
    return _path(case, "Edit-PartsDisable.json")


def frame_sheet(case, act):
    return _path(case, "Edit-FrameSheet-%s.json" % act)


def picked(case, act):
    return os.path.join(case, "clip-" + act, "keyframes.json")


def sheet(case, act):
    for p in (frame_sheet(case, act), picked(case, act)):
        if os.path.isfile(p):
            return json.load(open(p, encoding="utf-8"))
    return {}


def bone_keys(case, act):
    return _path(case, "Edit-BoneKeys-%s.json" % act)


def bone_key_files(case):
    return sorted(glob.glob(os.path.join(case, DIR, "Edit-BoneKeys-*.json")))
