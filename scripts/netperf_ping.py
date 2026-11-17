#!/bin/python3
import json
import argparse

# Set up argument parsing
parser = argparse.ArgumentParser()
parser.add_argument("-i", "--Input", help="Input File")
parser.add_argument("-o", "--Output", help="Output File", default="output.dat")
parser.add_argument("-k", "--DataKey", help="Data Key")

args = parser.parse_args()

# Open and decode the input JSON file
with open(args.Input) as jsonfile:
    decoder = json.JSONDecoder()
    jsonObj = decoder.decode(jsonfile.read())

# Open the output file
with open(args.Output, "a+") as datFile:
    datFile.seek(0)
    datFile.truncate()

    datLines = []

    for host in jsonObj:
        obj_list = jsonObj[host]  # List of address-port mappings
        for obj in obj_list:
            for address, port_data in obj.items():
                if isinstance(port_data, dict):  # Handle iperf3.json and iperfServer.json
                    for port, data_list in port_data.items():
                        destinationNode = data_list[0].get('destination_node', 'N/A')
                        initTs = float(data_list[1]['timestamp'])
                        for i in range(1, len(data_list)):
                            ts = float(data_list[i]['timestamp']) - initTs
                            data = data_list[i][args.DataKey]
                            datLines.append(f"{ts} {data}\n")
                elif isinstance(port_data, list):  # Handle ping.json
                    destinationNode = port_data[0].get('destination_node', 'N/A')
                    initTs = float(port_data[1]['timestamp'])
                    for i in range(1, len(port_data)):
                        ts = float(port_data[i]['timestamp']) - initTs
                        data = port_data[i][args.DataKey]
                        datLines.append(f"{ts} {data}\n")

    # Write collected lines to the output file
    datFile.writelines(datLines)
