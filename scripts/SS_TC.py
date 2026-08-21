#!/bin/python3
import json
import argparse


parser = argparse.ArgumentParser()
parser.add_argument("-i", "--Input", help = "Input File", )
parser.add_argument("-o", "--Output", help = "Output File", default="output.dat")
parser.add_argument("-k", "--DataKey", help = "Data Key")

args = parser.parse_args()

jsonfile = open(args.Input)

decoder = json.JSONDecoder()
jsonObj = decoder.decode(jsonfile.read())

datFile = open(args.Output, "a+")
datFile.seek(0)
datFile.truncate()

def getData(obj):
    datLines = []

    if 'destination_node' in obj[0]:
        destinationNode = obj[0]['destination_node']

    initTs = float(obj[1]['timestamp'])

    for i in range(1, len(obj)):
        ts = float(obj[i]['timestamp']) - initTs

        if args.DataKey in obj[i]:
            data = obj[i][args.DataKey]
            datLines.append(f"{ts} {data}\n")

        elif "tclasses" in obj[i]:
            for tc_name, tc_data in obj[i]["tclasses"].items():
                if args.DataKey in tc_data:
                    datLines.append(f"{ts} {tc_data[args.DataKey]}\n")

    return datLines





for host in jsonObj:
	obj = jsonObj[host][0]
	for address in obj:
		obj = obj[address]

		if type(obj) != list:
			for key in obj:
				datLines = getData(obj[key])
		else:
			datLines = getData(obj)


datFile.writelines(datLines)





jsonfile.close()
datFile.close()

