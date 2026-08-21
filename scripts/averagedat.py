#!/bin/python3

import argparse
from os import listdir
from os.path import isfile, join

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--Input", help="Input Directory")
parser.add_argument("-o", "--Output", help="Output File", default="output.dat")

args = parser.parse_args()

srcdir = args.Input

files = [f for f in listdir(srcdir) if isfile(join(srcdir, f))]

fileArray = []

for file in files:
    fileArray.append(open(join(srcdir, file)))

ts_vs_data = {}

for file in fileArray:
    lines = file.readlines()

    for line in lines:
        line = line.replace("\n", "")
        [ts, data] = line.split(" ")

        ts = round(float(ts), 4)
        if ts in ts_vs_data:
            ts_vs_data[ts].append(data)
        else:
            ts_vs_data[ts] = [data]

    file.close()


ts_vs_data = dict(sorted(ts_vs_data.items()))


datFile = open(args.Output, "w+")
lines = []
for ts in ts_vs_data:
    arr = ts_vs_data[ts]

    float_arr = [float(x) for x in arr]
    average = sum(float_arr) / len(float_arr)

    lines.append(str(ts) + " " + str(average) + "\n")


datFile.truncate()
datFile.seek(0)
datFile.writelines(lines)
datFile.close()
