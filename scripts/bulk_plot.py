import os
import numpy as np
import pandas as pd
import math
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy.interpolate import make_interp_spline, BSpline
#from statsmodels.distributions.empirical_distribution import ECDF
from scipy.stats import cumfreq
import seaborn as sns
from scipy.stats import binom
from scipy.stats import gaussian_kde
import sys
from collections.abc import Iterable
import matplotlib.ticker as ticker
from matplotlib.patches import Ellipse
import tkinter as tk
from tkinter import filedialog


scenerio="load testing "
aqm = "FQ-CoDel"
tcp="TcpCUBIC"

# === Constants ===
colors = plt.cm.Set1.colors#plt.cm.tab10.colors
single_plots = [
    {
        "file": "throughput.dat",
        "x_label": "Time (s)",
        "y_label": "Throughput (in Mbps)",
        "title": f"{tcp} with {aqm} - Throughput",
        "label" : "Throughput",
        "state_overlay": False,
        "multiple": True,
        "separate": True,
        #"separate_labels": ["Reno", "CUBIC"],
        "cumulative": False
    },
        {
        "file": "throughput.dat",
        "x_label": "Throughput (in Mbps)",
        "y_label": "CDF",
        "title": f"{tcp} - Throughput (CDF)",
        "label" : "Throughput (CDF)",
        "xlim" : [0,100],
        "state_overlay": False,
        "multiple": True,
        "cumulative": True,
        "legendLocation": "lower right"
    },
        {
        "file": "linkutil.dat",
        "x_label": "Time (s)",
        "y_label": "Link Utilization (%)",
        "title": f"{tcp} - Link Utilization (%)",
        "label" : "Link Utilization",
        "state_overlay": False,
        "cumulative": False,
    },
    {
        "file": "dqrate.dat",
        "legendLocation" : "upper center",
        "bbox": (0.5, -0.15),
        "legendCols":2,
        "x_label": "Time (s)",
        "y_label": "Dequeue Rate (Mb/sec)",
        "title": f"{tcp} - Dequeue Rate",
        "label" : "Dequeue Rate",
        "state_overlay": False,
        "cumulative": False,
    },
    {
        "file": "dqrate_20.dat",
        "x_label": "Time (s)",
        "y_label": "Dequeue Rate (Mb/sec)",
        "title": f"{tcp} - Dequeue Rate",
        "label" : "Dequeue Rate",
        "state_overlay": False,
        "cumulative": False,
        "xlim" : [0,100],
        "legendLocation" : "upper center",
        "bbox": (0.5, -0.15),
        "legendCols":2,
    },
    {
        "file": "rtt.dat",
        "x_label": "Time (s)",
        "y_label": "RTT (in ms)",
        "title": f"{tcp} - RTT",
        "hline": 40,
        "llabel" : "Reference RTT",
        "label" : "RTT",
        "state_overlay": False,
        "multiple": True
    },
     {
        "file": "inflight.dat",
        "x_label": "Time (s)",
        "y_label": "Bytes inflight (in bytes)",
        "title": f"{tcp} - Inflight",
        "label" : "Inflight",
        "state_overlay": False,
        "multiple": True
    },
     {
        "file": "cwnd.dat",
        "x_label": "Time (s)",
        "y_label": "Window size (in packets)",
        "title": f"{tcp} - Congestion window",
        "label" : "Cwnd",
        "xlim": [0,100],
        "state_overlay": False,
        "separate": True,
        # "separate_labels": ["Reno", "CUBIC"],
        "legendLocation": 'upper right' ,
        "multiple": True
    },
    {
        "file": "count.dat",
        "x_label": "Time (s)",
        "y_label": "Count value",
        "title": f"{tcp} - Count value",
        "label" : "Count value",
        "step" : True,
        "state_overlay": False
    },
   
    {
        "file": "qdelay.dat",
        "x_label": "Time (s)",
        "y_label": "Queue delay (in ms)",
        "title": f"{tcp} - Queue delay",
        "label" : "Queue delay",
        # "hline":5,
        # "llabel" : "Target delay",        
        "state_overlay": False,
        "probdist" : True
    },
    {
        "file": "queueSize.dat",
        "x_label": "Time (s)",
        "y_label": "Queue size (in packets)",
        "title": f"{tcp} - Queue size",
        "label" : "Queue size",
        "state_overlay": False,
        "probdist" : True
    },
    {
        "file": "dropnext.dat",
        "x_label": "Time (s)",
        "y_label": "Next Drop Time (in us)",
        "title": f"{tcp} - Next Drop Time",
        "label" : "Next Drop Time",
        "state_overlay": False,
        "interval" : True,
    },
     {
        "file": "qdrops.dat",
        "x_label": "Time (s)",
        "y_label": "Packets Dropped",
        "title": f"{tcp} - Packets Dropped",
        "label" : "Packet Drops",
        "state_overlay": True,
    },
    {
        "data": [
            {"file": "queueSize.dat", "label": "Queue size"},
            {"file": "count.dat", "label": "Count value", "step" : True}
        ],
        "x_label": "Time (s)",
        "y_label": "No. of Packets",
        "title": "Queue size vs Count value",
        "label" : "qlenvscount",
        "xlim": [0, 100],
        "state_overlay": True
    },
    {
        "file": "count.dat",
        "step" :  True,
        "x_label": "Time (s)",
        "y_label": "Count value",
        "title": "Count value",
        "label" : "Count Value",
        "xlim": [0, 100],
        "state_overlay": True
    },

    {
        "file": "bdp.dat",
        "x_label": "Time (s)",
        "y_label": "BDP (in bytes)",
        "title": f"{tcp} - BDP",
        "label" : "Estimated BDP",
        "hline": 50000,
        "llabel": "Theoretical BDP",
        "state_overlay": False,
        "multiple": True
    },

    {
        "file": "minRTT.dat",
        "x_label": "Time (s)",
        "y_label": "MinRTT (in ms)",
        "title": f"{tcp} - BDP",
        "label" : "Estimated MinRTT",
        "hline": 40,
        "llabel": "Reference RTT",
        "state_overlay": False,
        "multiple": True
    },
    {
        "file": "pdrop.dat",
        "x_label": "Time (s)",
        "y_label": "Drop Probability (BLUE)",
        "title": f"{tcp} - Random Drop probability of BLUE",
        "label" : "Drop probability",
        "state_overlay": False,
    },
]

#  {"file": "count_cobaltnoblue.dat", "label": "Cobatl with no Blue", "step" : True,}, 
#             {"file": "count_cobaltreset0.dat", "label": "Cobatl with no Blue \n(count reset to 0)", "step" : True,},  
#             {"file": "count_cobaltwait.dat", "label": "Cobatl with no Blue \n(With wait Interval)", "step" : True,}, 


def generate_plot_definitions(algos_list, file_prefix, *,
                               suffix=".dat",
                               step=False,
                               interval=False,
                               title_template="{labels}", 
                               label="plot",
                               params={}):
    """
    Generate a list of plot definitions dynamically.
    
    Parameters:
        algos_list: List of algorithm tuples to compare (id, label)
        file_prefix: Prefix of the data file (e.g. 'count', 'qdelay')
        suffix: File suffix (default: '.dat')
        step: Use step=True in the data block
        interval: Use interval=True in the data block
        title_template: Title string or template with {labels} placeholder
        x_label, y_label: Labels for axes
        label_prefix: Used to build the unique label ID
        xlim, ylim: Optional limits
        cumulative: Whether to set cumulative=True
        twoaxis: Whether this is a twoaxis plot
        additional_fields: Any extra fields to add to the top-level dict
    """
    defs = []
    for i, algo_group in enumerate(algos_list):
        data_block = []
        labels_for_title = []
        ids = []
        for algo_id, algo_label in algo_group:
            data_block.append({
                "file": f"{file_prefix}_{algo_id}{suffix}",
                "label": algo_label,
                **({"step": True} if step else {}),
                **({"interval": True} if interval else {})
            })
            labels_for_title.append(algo_label)
            ids.append(algo_id)

        plot_def = {
            "data": data_block,
            "title": title_template.format(labels=" and ".join(labels_for_title)),
            "label": f"{label}_{'_'.join(ids)}",
            "outputDir" : "_".join(ids),
            **params
        }
        defs.append(plot_def)
    return defs


cmp_defs = [
# {
#     "fileprefix" : "count",
#     "title_template":f"Comparison of count value trend over time ({scenerio})",
#     "step":True,
#     "interval":False,
#     "label":"count_cmp",
#     "plot_params": {
#         "x_label":"Time (s)", 
#         "y_label":"Count value",        
#         "xlim":[0, 100],              
#         "ylim":None,
#         "cumulative":False,
#         "twoaxis":False,
#         "bbox": (0.5, -0.30),
#         "legendCols": 2,
#         "legendLocation": "upper center",
#     }  
# },{
#     "fileprefix" : "count",
#     "title_template":f"Comparison of count value trend over time ({scenerio})",
#     "step":True,
#     "interval":False,
#     "label":"count_20_cmp",
#     "plot_params" : {
#         "x_label":"Time (s)",
#         "y_label":"Count value",
#         "xlim":[0, 20],                              
#         "ylim":None,
#         "cumulative":False,
#         "twoaxis":False,
#         "additional_fields":None
#     }
# },
{
    "fileprefix" : "pdrop",
    "title_template":f"Comparison of PDrop value trend over time ({scenerio})",
    #"step":True,
    "interval":False,
    "label":"pdrop_20_cmp",
    "plot_params" : {
        "x_label":"Time (s)",
        "y_label":"Drop probability",
        "xlim":[0, 100],                              
        "ylim":None,
        "cumulative":False,
        "twoaxis":False,
        "additional_fields":None,
        "bbox": (0.5, -0.15),
        "legendCols": 2,
        "legendLocation": "upper center",
    }
},
{
    "fileprefix" : "pdrop",
    "title_template":f"Comparison of PDrop value trend over time ({scenerio})",
    #"step":True,
    "interval":False,
    "label":"pdrop_5_cmp",
    "plot_params" : {
        "x_label":"Time (s)",
        "y_label":"Drop probability",
        "xlim":[0, 5],                              
        "ylim":None,
        "cumulative":False,
        "twoaxis":False,
        "additional_fields":None,
        "bbox": (0.5, -0.15),
        "legendCols": 2,
        "legendLocation": "upper center",
    }
},
{
    "fileprefix" : "count",
    "title_template":f"Comparison of count value trend over time ({scenerio})",
    #"step":True,
    "interval":False,
    "label":"count_cmp",
    "plot_params" : {
        "x_label":"Time (s)",
        "y_label":"Count Value",
        "ylim":None,
        "cumulative":False,
        "twoaxis":False,
        "additional_fields":None,
        "bbox": (0.5, -0.15),
        "legendCols": 2,
        "legendLocation": "upper center",
    }
},
{
    "fileprefix" : "pdrop",
    "title_template":f"Comparison of PDrop value trend over time ({scenerio})",
    #"step":True,
    "interval":False,
    "label":"pdrop_cmp",
    "plot_params" : {
        "x_label":"Time (s)",
        "y_label":"Drop probability",
        "ylim":None,
        "cumulative":False,
        "twoaxis":False,
        "additional_fields":None,
        "bbox": (0.5, -0.15),
        "legendCols": 2,
        "legendLocation": "upper center",
    }
},
{
    "fileprefix" : "pieqdelay",
    "title_template":f"Comparison of Qdelay Estimated by PIE ({scenerio})",
    #"step":True,
    "interval":False,
    "label":"pieqdelay_20_cmp",
    "plot_params" : {
        "x_label":"Time (s)",
        "y_label":"Qdelay Estimated",
        "xlim":[0, 100],                              
        "ylim":None,
        "cumulative":False,
        "twoaxis":False,
        "additional_fields":None,
        "bbox": (0.5, -0.15),
        "legendCols": 2,
        "legendLocation": "upper center",
    }
},
{
    "fileprefix" : "pieqdelay",
    "title_template":f"Comparison of Qdelay Estimated by PIE ({scenerio})",
    #"step":True,
    "interval":False,
    "label":"pieqdelay_cmp",
    "plot_params" : {
        "x_label":"Time (s)",
        "y_label":"Qdelay Estimated",
        "ylim":None,
        "cumulative":False,
        "twoaxis":False,
        "additional_fields":None,
        "bbox": (0.5, -0.15),
        "legendCols": 2,
        "legendLocation": "upper center",
    }
},
{
    "fileprefix" : "dropnext",
    "title_template": f"Next Drop Time Distribution ({scenerio})",
    "label" : "drop_next_gap_cmp (0 - 5 seconds)",
    "interval" : True,
    "plot_params" : {
        "x_label": "Next Drop Time (in seconds)",
        "y_label": "Algorithms",
        "xlim": [0, 5000000], 
        "state_overlay": False,
        "cumulative": False
    }
},
{
    "fileprefix" : "dropnext",
    "title_template": f"Next Drop Time Distribution ({scenerio})",
    "label" : "drop_next_gap_cmp (0 - 10 seconds)",
    "interval" : True,
    "plot_params":{
        "x_label": "Next Drop Time (in seconds)",
        "y_label": "Algorithms",
        "xlim": [0, 10000000],
        "state_overlay": False,
        "cumulative": False
    }
},
    {
    "fileprefix" : "dropnext",
    "title_template": "Next Drop Time Distribution",
    "label" : f"drop_next_gap_cmp (0 - 1.5 seconds) ({scenerio})",
    "interval" : True,
    "plot_params" : {
        "x_label": "Next Drop Time (in seconds)",
        "y_label": "Algorithms",
        "xlim": [0, 1500000],  
        "state_overlay": False,
        "cumulative": False
    }
    },
    {
        "fileprefix" : "dropnext",
        "title_template": f"Next Drop Time Distribution (10 - 15 seconds) ({scenerio})",
        "label" : "drop_next_gap_10_20_cmp",
        "interval" : True,
        "plot_params" : {
            "x_label": "Next Drop Time (in seconds)",
            "y_label": "Algorithms",
            "xlim": [10000000, 15000000],
            "state_overlay": False,
            "cumulative": False
            }
        },
        {
        "fileprefix" : "dropnext",
        "title_template": f"Next Drop Time Distribution (0 - 20 seconds) ({scenerio})",
        "label" : "drop_next_gap_cmp",
        "interval" : True,
        "plot_params" : {
            "x_label": "Next Drop Time (in seconds)",
            "y_label": "Algorithms",
            "xlim": [0, 20000000],
            "state_overlay": False,
            "cumulative": False
            }
        },
        {
        "fileprefix" : "qdrops",
        "title_template": f"Cumulative packet drops ({scenerio})",
        "label" : "qdrops_cmp",
        "plot_params": {
            "x_label": "Time (s)",
            "y_label": "Packets Dropped",
            "legendLocation" : "upper center",
            "bbox": (0.5, -0.15),
            "legendCols": 2,
            "state_overlay": False,
            "cumulative": False
        }
        },
        {
        "fileprefix" : "qdrops",
        "title_template": f"Cumulative packet drops (After dequeue) ({scenerio})",
        "label" : "qdrops_20_cmp",
        "plot_params": {
            "x_label": "Time (s)",
            "y_label": "Packets Dropped",
            "xlim": [0, 100],
            "legendLocation" : "upper center",
            "bbox": (0.5, -0.15),
            "legendCols": 2,
            "state_overlay": False,
            "cumulative": False
        }
        },
        {
        "fileprefix" : "linkutil",
        "title_template": f"Comparison of linkutil trend over time ({scenerio})",
        "label" : "linkutil_cmp",
        "plot_params" : {
            "x_label": "Time (s)",
            "y_label": "Link Utilization (%)",                        
            "state_overlay": False,
            "bbox": (0.5, -0.15),
            "legendCols": 2,
            "legendLocation": "upper center",
        }
        },
        {
        "fileprefix" : "qdelay",
        "title_template": f"Comparison of queue delay trend over time ({scenerio})",
        "label" : "qdelay_cmp",        
        "plot_params" : {
            "x_label": "Time (s)",
            "y_label": "Queue delay (in ms)",
            # "hline":15,
            "percentile": True,
            # "llabel" : "Target delay",            
            "state_overlay": False,
            "bbox": (0.5, -0.15),
            "legendCols": 2,
            "legendLocation": "upper center",
        }
        },
        
        {
        "fileprefix" : "qdelay",
        "title_template": f"Comparison of queue delay trend over time ({scenerio})",
        "label" : "qdelay_20_cmp",
        "plot_params" : {
            "x_label": "Time (s)",
            "y_label": "Queue delay (in ms)",
            # "hline":15,
            # "llabel" : "Target delay",            
            "xlim": [0, 100],
            "state_overlay": False,
            "bbox": (0.5, -0.15),
            "legendCols": 2,
            "legendLocation": "upper center",
        }
        },
        {
        "fileprefix" : "qdelay",
        "title_template": f"Comparison of queue delay trend over time ({scenerio})",
        "label" : "qdelay_5_cmp",
        "plot_params" : {
            "x_label": "Time (s)",
            "y_label": "Queue delay (in ms)",
            # "hline":15,
            # "llabel" : "Target delay",            
            "xlim": [0, 5],
            "state_overlay": False,
            "bbox": (0.5, -0.15),
            "legendCols": 2,
            "legendLocation": "upper center",
        }
        },
        {
        "fileprefix" : "qdelay",
        "title_template": f"Cumulative Distribution Function (CDF) of Queue delays \n({scenerio})",
        "label" : "qdelay_cdf_50_cmp",
        "plot_params" : {
            "cumulative": True,
            "legendLocation" : "lower right",
            "state_overlay": False,
            # "vline":5,
            # "llabel" : "Target delay",
            "xlim": [0, 50],
            "ylim": [0, 1],
            "x_label": "Queue delay (in ms)",
            "y_label": "CDF",
            "state_overlay": False
        }
        }, 
        # {
        # "fileprefix" : "qdelay",
        # "title_template": f"Cumulative Distribution Function (CDF) of Queue delays \n({scenerio})",
        # "label" : "qdelay_cdf_500_cmp",
        # "plot_params" : {
        #     "cumulative": True,
        #     "legendLocation" : "lower right",
        #     "state_overlay": False,
        #     "vline":5,
        #     "llabel" : "Target delay",
        #     "xlim": [0, 500],
        #     "ylim": [0, 1],
        #     "x_label": "Queue delay (in ms)",
        #     "y_label": "CDF",
        #     "state_overlay": False
        # }
        # },       
        {
        "fileprefix" : "qdelay",
        "title_template": f"Cumulative Distribution Function of Queue delays \n({scenerio})",
        "label" : "qdelay_cdf_cmp",
        "plot_params" : {
            "cumulative": True,
            "legendLocation" : "lower right",
            "state_overlay": False,            
            "ylim": [0, 1],
            "x_label": "Queue delay (in ms)",
            "y_label": "CDF",
            "state_overlay": False
        }
        },
        {
          "fileprefix" : "throughput",
        "title_template": f"Cumulative Distribution Function of Throughput \n({scenerio})",
        "label" : "throughput_cdf_cmp",
        "plot_params" : {
            "cumulative": True,
            "legendLocation" : "lower right",
            "state_overlay": False,
            "ylim": [0, 1],
            "x_label": "Throughput (in Mbps)",
            "y_label": "CDF",
            "xlim" : [0,100],
            "state_overlay": False
        }  
        },
        {
          "fileprefix" : "throughput",
        "title_template": f"Throughput \n({scenerio})",
        "label" : "throughput_synchronous",
        "plot_params" : {
            "cumulative": False,
            "legendLocation" : "lower right",
            #bbox_to_anchor=plot_def.get("legend_bbox", (1.0, 0.12)),
            #"bbox": (1.5, 0.15),
            "legendCols": 1,
            "legend_fontsize": 30,
            "legend_linewidth": 3.5,
            "legend_handlelength": 1.2,
            "legend_handletextpad": 0.6,
            "legend_labelspacing": 0.1,
            "legend_borderpad": 0.5,
            "legend_frame": False,
            "markerfirst": False,
            "state_overlay": False,
            "x_label": "Time (in Seconds)",
            "y_label": "Throughput (in Mbps)",
            "xlabel_fontsize": 26,
            "ylabel_fontsize": 26,
            "tick_fontsize": 22,
            "label_fontsize": 24,
            "tick_length": 2.5,   # Default was 4 (Smaller = shorter ticks)
            "tick_width": 1.0,

            #"xlabel_fontweight": "bold",
            #"ylabel_fontweight": "bold",
            #"tick_fontweight": "bold",
            "xlim": [0, 100],
            "ylim": [0, 2.0],
            "xticks": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
            "yticks": [0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0]
        }  
        },
            {
          "fileprefix" : "dropnext",
        "title_template": f"dropnext \n({scenerio})",
        "label" : "dropnext_cmp",
        "plot_params" : {
            "cumulative": False,
            "legendLocation" : "upper center",
            "bbox": (0.5, -0.15),
            "legendCols":2,
            "state_overlay": False,
            "x_label": "Time (s)",
            "y_label": "dropnext (in packets)",
            "xlim": [0, 100],
            "state_overlay": False
        }  
        },
        {
          "fileprefix" : "throughput",
        "title_template": f"Cumulative Distribution Function of Throughput \n({scenerio})",
        "label" : "throughput_20_cdf_cmp",
        "plot_params" : {
            "cumulative": True,
            "legendLocation" : "lower right",
            "state_overlay": False,
            "xlim": [0,3],
            "ylim": [0, 1],
            "x_label": "Throughput (in Mbps)",
            "y_label": "CDF",
            "state_overlay": False
        }  
        },
         {
        "fileprefix" : "queueSize",
        "title_template": f"Comparison of queue size trend over time ({scenerio})",
        "label" : "qsize_cmp",
        "plot_params" : {
           "x_label": "Time (s)",
            "y_label": "Queue Size (in packets)",            
            "state_overlay": False
        }
        },
         {
        "fileprefix" : "queueSize",
        "title_template": f"Cumulative density function of Queue Sizes ({scenerio})",
        "label" : "qsize_cdf_cmp",
        "plot_params" : {
           "cumulative": True,
            "legendLocation" : "lower right",
            "state_overlay": False,            
            "ylim": [0, 1],
            "x_label": "Queue size (in packets)",
            "y_label": "CDF",
            "state_overlay": False
        }
        },
        {
        "fileprefix" : "cwnd",
        "title_template": f"Comparison of cwnd trend over time ({scenerio})",
        "label" : "cwnd",
        "plot_params" : {
           "x_label": "Time (s)",
            "y_label": "cwnd (in packets)",            
            "state_overlay": False
        }
        },
]

def compare_flows(
    file1, 
    file2, 
    dest, 
    total_flows=None, 
    ylabel="Queue Delay (ms)",
    labels=("FQ-PIE (Timestamp)", "FQ-PIE (Little's Law)"), 
    title="Per Flow queue delay"
):
    """
    Compare two files by plotting Delay vs Time for each flow in subplots.

    Args:
        file1 (str): Path to first file (space-separated: Time, Flow, Delay).
        file2 (str): Path to second file (optional).
        dest (str): Output path to save the plot.
        total_flows (int, optional): Total number of flows. Detected automatically if None.
        labels (tuple): Labels for file1 and file2.
        title (str, optional): Title for the figure.
    """
    # --- Check which files exist ---
    if not os.path.exists(file1):
        print(f"[Error] File not found: {file1}")
        return
    has_file2 = os.path.exists(file2) if file2 else False

    # --- Read files ---
    df1 = pd.read_csv(file1, sep=r'\s+', names=["Time", "Flow", "Delay"])
    df2 = pd.read_csv(file2, sep=r'\s+', names=["Time", "Flow", "Delay"]) if has_file2 else pd.DataFrame()

    # --- Determine flows ---
    if total_flows is not None:
        flows = range(1, total_flows + 1)
    else:
        flows = sorted(set(df1["Flow"].unique()) | (set(df2["Flow"].unique()) if has_file2 else set()))
    n_flows = len(flows)

    # --- Subplot grid ---
    rows = math.ceil(n_flows / 2)
    cols = 2
    fig, axes = plt.subplots(rows, cols, figsize=(12, rows * 3), sharex=True, sharey=True)
    axes = axes.flatten()

    # --- Plot per flow ---
    for i, flow in enumerate(flows):
        ax = axes[i]
        flow1 = df1[df1["Flow"] == flow]
        flow2 = df2[df2["Flow"] == flow] if has_file2 else pd.DataFrame()

        if not flow1.empty:
            ax.plot(flow1["Time"], flow1["Delay"], color=colors[1], label=f"{labels[0]}")
        if has_file2 and not flow2.empty:
            ax.plot(flow2["Time"], flow2["Delay"], color=colors[0], label=f"{labels[1]}")

        ax.set_title(f"Flow {flow}")
        ax.set_xlabel("Time (s)")
        ax.set_ylabel(ylabel)
        ax.legend()

    # --- Remove empty subplots ---
    for j in range(i + 1, len(axes)):
        fig.delaxes(axes[j])

    # --- Title and layout ---
    if title:
        fig.suptitle(title, fontsize=14)
    plt.tight_layout()
    plt.savefig(dest)
    plt.close(fig)





def add_dashed_line(ax, value, orientation='vertical', color='gray', linestyle='--', linewidth=3, label=None):
    """
    Add a dashed line to a matplotlib axis.

    Parameters:
        ax          : matplotlib Axes object
        value       : Position of the line (x or y value)
        orientation : 'vertical' or 'horizontal'
        color       : Line color (default: 'gray')
        linestyle   : Line style (default: dashed)
        linewidth   : Line width (default: 1)
        label       : Optional label for the legend
    """
    if orientation == 'vertical':
        ax.axvline(x=value, color=color, linestyle=linestyle, linewidth=linewidth, label=label)
    elif orientation == 'horizontal':
        ax.axhline(y=value, color=color, linestyle=linestyle, linewidth=linewidth, label=label)
    else:
        raise ValueError("orientation must be 'vertical' or 'horizontal'")


# === GUI folder selector ===
def select_folder():
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Select directory containing data files")
    if not folder:
        print("No directory selected.")
        exit()
    return folder, os.path.join(folder, "plots")

# === Load state.dat if available ===
def load_state_regions(state_path):
    if not os.path.exists(state_path):
        return []
    state_data = np.loadtxt(state_path)
    try:
        x, y = state_data[:, 0], state_data[:, 1]
        regions = [(0, x[0], 0)]
    except:
        return []
    for i in range(len(y) - 1):
        regions.append((x[i], x[i + 1], y[i]))
    return regions

# === Draw background based on state ===
def draw_state_overlay(ax, regions):
    bg_patches = {}
    for start_x, end_x, state in regions:
        color = (0.8, 1, 0.8) if state == 0 else (1, 0.8, 0.8)
        label = "Non-Dropping" if state == 0 else "Dropping phase"
        ax.axvspan(start_x, end_x, facecolor=color, edgecolor='none', alpha=0.5)
        if label not in bg_patches:
            bg_patches[label] = Patch(facecolor=color, edgecolor='none', alpha=0.5, label=label)
    return list(bg_patches.values())

def generateCdf(data):
    sorted_data = np.sort(data)
    cdf = np.arange(1, len(data) + 1) / len(data)
    unique_x = np.unique(sorted_data)
    max_y = [np.max(cdf[sorted_data == val]) for val in unique_x]
    x,y = unique_x, max_y
    # r = cumfreq(data, numbins=25)
    # x = r.lowerlimit + np.linspace(0, r.binsize * r.cumcount.size, r.cumcount.size)
    # c = r.cumcount / r.cumcount[-1]

    #Smooth using spline
    x_dense = np.linspace(x.min(), x.max(), 500)  # 300 points for smooth curve
    spline = make_interp_spline(x, y, k=3)  # Cubic spline
    y_smooth = spline(x_dense)

    # try:
    #     spline = make_interp_spline(x, y, k=3)  # Cubic spline
    #     y_smooth = spline(x_dense)
    # except ValueError:
    #     # If not enough unique points for spline, fall back to original
    #     x_dense, y_smooth = x, y

    return x_dense, y_smooth#list(map(lambda x: x if x <= 1 else 1.0,y_smooth))

def plot_cdf(data, label, output_path):
   
    plt.figure()
    x,y = generateCdf(data)
    # kde = gaussian_kde(data)
    # x = np.linspace(0, data.max(), 1000)  # Start from 0
    # y = kde(x)
    plt.plot(x, y, linewidth=1.5)
    #sns.kdeplot(data=data, cumulative=True)
    #sns.ecdfplot(data)
    #plt.xlim(left=0)
    plt.xlim(0, 100)
    plt.xlabel(label)
    plt.ylabel("CDF")
    plt.title(f"CDF of {label}")
    plt.grid(False)
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Saved: {os.path.basename(output_path)}")
    plt.close()


def plot_pdf(data, label, output_path):
    plt.figure()
    
    plt.hist(data, bins=np.arange(0,400,5), density=True, alpha=0.7)
    #sns.displot(data, kde=True, bins=15)
    #plt.bar_label(bars)
    plt.xlabel(label)
    plt.ylabel("PDF")
    plt.title(f"PDF of {label}")
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path)
    print(f"Saved: {os.path.basename(output_path)}")
    plt.close()

def load_qdelay_samples(qdelay_file):
    """
    Loads queue delay samples from qdelay_*.dat
    Returns: 1D numpy array (delay in ms)
    """
    data = np.loadtxt(qdelay_file)
    if data.ndim == 1:
        return np.array([])
    return data[:, 1]   # second column = delay (ms)

def plot_qdelay_boxplot(base_dir, algos, labels, output_path):
    all_data = []
    valid_labels = []

    for algo, label in zip(algos, labels):
        path = os.path.join(base_dir, f"qdelay_{algo}.dat")
        if not os.path.exists(path):
            print(f"Skipping {algo}: missing qdelay file")
            continue

        qdelays = load_qdelay_samples(path)
        if len(qdelays) == 0:
            continue

        all_data.append(qdelays)
        valid_labels.append(label)

    if not all_data:
        print("No valid qdelay data found for box plot.")
        return

    fig, ax = plt.subplots(figsize=(8, 6))

    bp = ax.boxplot(
        all_data,
        labels=valid_labels,
        showfliers=True,
        patch_artist=True,
        widths=0.6,
    )

    # Coloring
    for i, box in enumerate(bp["boxes"]):
        box.set(facecolor=colors[i % len(colors)], alpha=0.6)

    for element in ["whiskers", "caps", "medians"]:
        for item in bp[element]:
            item.set(color="black", linewidth=1.2)

    ax.set_ylabel("Queue Delay (ms)", fontsize=24)
    
    #ax.set_title("Queue Delay Distribution Across Algorithms")
    ax.grid(axis="y", linestyle="--", alpha=0.6)
    plt.xticks(fontsize=14)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()


def compute_ellipse_params(points, nstd=1.0):
    """
    points: Nx2 array (delay, throughput)
    nstd: number of standard deviations
    Returns: width, height, angle (degrees)
    """
    cov = np.cov(points, rowvar=False)
    vals, vecs = np.linalg.eigh(cov)
    order = vals.argsort()[::-1]
    vals, vecs = vals[order], vecs[:, order]

    angle = np.degrees(np.arctan2(vecs[1, 0], vecs[0, 0]))
    width, height = 2 * nstd * np.sqrt(vals)

    return width, height, angle

def plot_ellipses_from_qdelay_throughput(
    base_dir,
    algos,
    labels,
    output_path,
    nstd=1.0
):
    fig, ax = plt.subplots(figsize=(8, 6))

    for i, algo in enumerate(algos):
        qdelay_file = os.path.join(base_dir, f"qdelay_{algo}.dat")
        throughput_file = os.path.join(base_dir, f"throughput_{algo}.dat")

        if not (os.path.exists(qdelay_file) and os.path.exists(throughput_file)):
            print(f"Skipping {algo}: missing files")
            continue

        data = load_interpolated_delay_throughput(qdelay_file, throughput_file)

        mean = data.mean(axis=0)
        width, height, angle = compute_ellipse_params(data, nstd=nstd)

        ellipse = Ellipse(
            xy=mean,
            width=width,
            height=height,
            angle=angle,
            edgecolor=colors[i % len(colors)],
            facecolor='none',
            linewidth=2,
            label=labels[i]
        )

        ax.add_patch(ellipse)
        ax.scatter(mean[0], mean[1], color=colors[i % len(colors)], s=25)

    ax.set_xlabel("Average Queue Delay (ms)")
    ax.set_ylabel("Throughput (Mbps)")
    ax.set_title("Delay–Throughput Ellipse Comparison")
    ax.legend()
    ax.grid(True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    print("Saved ellipsis")


def load_interpolated_delay_throughput(qdelay_file, throughput_file):
    """
    Interpolates queue delay at throughput timestamps.

    Returns: Nx2 array [delay(ms), throughput(Mbps)]
    """

    # Load data
    tq, qdelay = np.loadtxt(qdelay_file, unpack=True)
    tt, throughput = np.loadtxt(throughput_file, unpack=True)

    # Interpolate queue delay at throughput timestamps
    qdelay_interp = np.interp(
        tt,
        tq,
        qdelay,
        left=qdelay[0],
        right=qdelay[-1]
    )

    # Units (match your original scripts)
    delay_ms = qdelay_interp          # already ms
    throughput_mbps = throughput      # already Mbps in your example

    return np.column_stack((delay_ms, throughput_mbps))


# === Apply cumulative logic if needed ===
def compute_cumulative(y):
    y_cum = [y[0]]
    for i in range(1, len(y)):
        y_cum.append(y_cum[-1] + (y[i] - y[i-1]) if y[i] > y[i-1] else y_cum[-1])
    return np.array(y_cum)


# === Plot single or multiple series from a file ===
def plot_series(ax, folder_path, entry, plot_def, color_offset=0, return_data=False):
    plotted = False
    data_list = []
    def process_and_plot(x, y, label, j = 0):
        if plot_def.get("cumulative", False):     
           sns.kdeplot(data=y, cumulative=True,color=colors[(j + color_offset) % len(colors)], linewidth=3, label=label)
           #x,y = generateCdf(y)
           #plt.plot(x, y, color=colors[(j + color_offset) % len(colors)], linewidth=1, label=label)
           data_list.extend(y)
           #ax.set_xlim(left=0)
           ax.set_xlim(0,100)
           return
        plot_fn = ax.step if entry.get("step", False) else ax.plot
        plot_fn(x, y, color=colors[(j + color_offset) % len(colors)], linewidth=1, label=label)
        data_list.extend(y)
        

    def plot_interval(x,y, label,j = 0):
        # Step plot to emphasize horizontal intervals
        #ax.step(x, np.ones(len(x)), where='post', color='blue', linewidth=2, label=label)
        # Scatter points to indicate the data points clearly
        ax.scatter(y, np.array([label] * len(x)), color=colors[(j + color_offset) % len(colors)], s=1, label=label, zorder=5)
        ax.tick_params(axis='y', labelsize=10, pad=10)  
        # Annotate gaps if needed
        # for i in range(1, len(x)):
        #     gap_x = (x[i] + x[i-1]) / 2
        #     gap_y = max(y[i], y[i-1]) * 1.01
        #     ax.annotate(f"{x[i]-x[i-1]:.2f}", xy=(gap_x, gap_y),
        #                 ha='center', fontsize=8, color='gray')
    percentile = None
    if entry.get("multiple", False):
        all_x = []
        all_y = []
        j = 0
        while True:
            file = entry["file"].replace(".dat", f"_{j}.dat")
            path = os.path.join(folder_path, file)
            if not os.path.exists(path):
                break
            x, y = np.loadtxt(path, unpack=True)
            if not isinstance(y, Iterable):
                break
            all_x.append(x)
            all_y.append(y)
            j += 1
    
        if j == 0:
            print("No files found.")
        elif entry.get("separate", False):
            i = 0            
            for x, y in zip(all_x, all_y):                
                label = entry.get("separate_labels")[i] if entry.get("separate_labels") is not None else f"{entry.get('label', 'Average')}_{i}"
                if entry.get("interval", False):
                    plot_interval(x, y, label, i)
                else:
                    process_and_plot(x, y, label, i)
                i+=1
            plotted = True
        else:
            # Interpolate all y-values on a common x-axis
            common_x = all_x[0]
            interpolated_ys = []

            for xi, yi in zip(all_x, all_y):
                if not np.array_equal(xi, common_x):
                    yi_interp = np.interp(common_x, xi, yi)
                else:
                    yi_interp = yi
                interpolated_ys.append(yi_interp)

            # Convert to numpy array and average across all y-values
            avg_y = np.mean(interpolated_ys, axis=0)

            # Plot the average curve
            label = entry.get("label", "Average")
            if entry.get("interval", False):
                plot_interval(common_x, avg_y, label)
            else:
                process_and_plot(common_x, avg_y, label)
            plotted = True
    else:
        file = entry["file"]
        path = os.path.join(folder_path, file)
        if not os.path.exists(path):
            return (None, [], percentile)
        x,y = 0,0
        try:
            x, y = np.loadtxt(path, unpack=True)
        except:
            return (None,[], percentile)
        if not isinstance(y, Iterable):
            return (None,[], percentile)
        
        if file.startswith("linkutil"):
            y = y / 10
        if entry.get("interval", False):
            plot_interval(x, y, entry["label"])
        else:
            process_and_plot(x, y, entry["label"])
        if(plot_def.get("percentile",False)):
            percentile = {
                "Median" : np.median(y),
                "90th" : np.percentile(y,90),
                "95th" : np.percentile(y,95),
                "99th" : np.percentile(y,99),
            }
        plotted = True
    return (percentile, plotted, np.array(data_list) if return_data else None)

def plot_percentile_bar(data, path):
    labels = [d["label"] for d in data]           # Algo1, Algo2, ...
    percentiles = ["Median", "90th", "95th", "99th"]  # Groups on X-axis

    # Build data matrix: Each row corresponds to a label (algorithm)
    values = []
    for d in data:
        values.append([d["data"][p] for p in percentiles])

    values = np.array(values)  # Shape: (num_algorithms, 4 percentiles)

    x = np.arange(len(percentiles))  # X-axis: median, 90, 95, 99
    width = 0.2  # Width of each bar

    fig, ax = plt.subplots(figsize=(10, 6))

    # Plot one bar per algorithm (label)
    for i, label in enumerate(labels):
        bars = ax.bar(x + i * width, values[i], width, label=label, color=colors[i])

        # Add values on top of each bar
        ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)

    # Labels and legend
    ax.set_xlabel('Percentiles')
    ax.set_ylabel('Queue Delay (in ms)')
    ax.set_title('Queue Delay Percentiles Across Algorithms')
    ax.set_xticks(x + width * (len(labels) - 1) / 2)
    ax.set_xticklabels(percentiles)
    ax.legend(title="Algorithms")

    plt.grid(axis='y', linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(path, bbox_inches="tight", pad_inches=0.15)
    plt.close()    

# === Main plot dispatcher ===
def generate_plots(folder_path, plot_dir, plots_to_generate, regions):
    plot_index = 1

    # --------------------------------------------------
    # Global font
    # --------------------------------------------------
    plt.rcParams.update({
        "font.family": "Liberation Serif",
        "mathtext.fontset": "stix",
    })

    for plot_def in plots_to_generate:

        fig, ax = plt.subplots(constrained_layout=True)
        ax2 = None
        handles = []
        plotted = False
        percentiles = []

        # --------------------------------------------------
        # Load and plot data
        # --------------------------------------------------

        if "data" in plot_def:

            all_data = []
            use_twoaxis = plot_def.get("twoaxis", False)

            for i, entry in enumerate(plot_def["data"]):

                ax2 = ax.twinx() if use_twoaxis and i == 1 else ax2

                percentile, plotted_current, data = plot_series(
                    ax2 if use_twoaxis and i == 1 else ax,
                    folder_path,
                    entry,
                    plot_def,
                    i,
                    return_data=True
                )

                if percentile is not None:
                    percentiles.append({
                        "label": entry.get("label", "Average"),
                        "data": percentile
                    })

                if plotted_current:
                    all_data.extend(data)
                    plotted = True

        else:

            entry = {
                "file": plot_def["file"],
                "label": plot_def.get(
                    "label",
                    os.path.basename(plot_def["file"])
                ),
                "step": plot_def.get("step", False),
                "multiple": plot_def.get("multiple", False),
                "separate": plot_def.get("separate", False),
                "separate_labels": plot_def.get(
                    "separate_labels",
                    None
                ),
                "percentile": plot_def.get(
                    "percentile",
                    False
                ),
            }

            percentile, plotted, data = plot_series(
                ax,
                folder_path,
                entry,
                plot_def,
                return_data=True
            )

            if percentile is not None:
                percentiles.append({
                    "label": entry.get("label", "Average"),
                    "data": percentile
                })

            if plotted:
                all_data = data

        # --------------------------------------------------
        # Reference lines
        # --------------------------------------------------

        if plot_def.get("vline", -1) > 0:
            add_dashed_line(
                ax,
                plot_def.get("vline", -1),
                label=plot_def.get(
                    "llabel",
                    "Reference"
                )
            )

        if plot_def.get("hline", -1) > 0:
            add_dashed_line(
                ax,
                plot_def.get("hline", -1),
                "horizontal",
                label=plot_def.get(
                    "llabel",
                    "Reference"
                )
            )

        # --------------------------------------------------
        # Skip if no valid data
        # --------------------------------------------------

        if not plotted:
            print(
                f"Skipping plot: "
                f"{plot_def.get('label', 'Unnamed')} "
                f"(No valid data)"
            )
            plt.close()
            continue

        # --------------------------------------------------
        # State overlay
        # --------------------------------------------------

        if plot_def.get("state_overlay", False) and regions:
            handles += draw_state_overlay(ax, regions)

        # --------------------------------------------------
        # Font sizes
        # --------------------------------------------------

        label_fontsize = plot_def.get(
            "label_fontsize",
            24
        )

        xlabel_fontsize = plot_def.get(
            "xlabel_fontsize",
            label_fontsize
        )

        ylabel_fontsize = plot_def.get(
            "ylabel_fontsize",
            label_fontsize
        )

        tick_fontsize = plot_def.get(
            "tick_fontsize",
            20
        )

        xlabel_fontweight = plot_def.get(
            "xlabel_fontweight",
            "bold"
        )

        ylabel_fontweight = plot_def.get(
            "ylabel_fontweight",
            "bold"
        )

        tick_fontweight = plot_def.get(
            "tick_fontweight",
            "bold"
        )

        # --------------------------------------------------
        # Axis labels
        # --------------------------------------------------

        ax.set_xlabel(
            plot_def.get(
                "x_label",
                "Time"
            ),
            fontsize=xlabel_fontsize,
            fontweight=xlabel_fontweight,
            labelpad=plot_def.get(
                "xlabel_pad",
                10
            )
        )

        if plot_def.get("twoaxis", False):

            labs = plot_def.get(
                "y_label",
                "Value"
            )

            ax.set_ylabel(
                labs[0],
                fontsize=ylabel_fontsize,
                labelpad=plot_def.get(
                    "ylabel_pad",
                    20
                )
            )

            ax2.set_ylabel(
                labs[1],
                fontsize=ylabel_fontsize,
                labelpad=plot_def.get(
                    "ylabel_pad",
                    20
                )
            )

        else:

            ax.set_ylabel(
                plot_def.get(
                    "y_label",
                    "Value"
            ),
            fontsize=ylabel_fontsize,
            fontweight=ylabel_fontweight,
            labelpad=plot_def.get(
                "ylabel_pad",
                20
            )
            )
        # --------------------------------------------------
        # Axis limits
        # --------------------------------------------------

        if (
            "xlim" in plot_def
            and plot_def["xlim"] is not None
        ):

            ax.set_xlim(
                plot_def["xlim"]
            )

            if plot_def["xlim"][1] > 100000:

                plt.ticklabel_format(
                    style="sci",
                    axis="x",
                    scilimits=(6, 6)
                )

        if (
            "ylim" in plot_def
            and plot_def["ylim"] is not None
        ):

            ax.set_ylim(
                plot_def["ylim"]
            )

        # --------------------------------------------------
        # X-axis ticks
        # --------------------------------------------------

        if (
            "xticks" in plot_def
            and plot_def["xticks"] is not None
        ):

            ax.set_xticks(
                plot_def["xticks"]
            )

        # --------------------------------------------------
        # Y-axis ticks
        # --------------------------------------------------

        if (
            "yticks" in plot_def
            and plot_def["yticks"] is not None
        ):

            ax.set_yticks(
                plot_def["yticks"]
            )

        # --------------------------------------------------
        # Tick font size
        # --------------------------------------------------

        ax.tick_params(
            axis="both",
            which="major",
            direction="in",
            labelsize=tick_fontsize,
            width=plot_def.get(
                "tick_width",
                1.0
            ),
            length=plot_def.get(
                "tick_length",
                2.5
            )
        )
        for label in ax.get_xticklabels():
            label.set_fontweight(tick_fontweight)

        for label in ax.get_yticklabels():
            label.set_fontweight(tick_fontweight)
        # Secondary axis
        if (
            plot_def.get("twoaxis", False)
            and ax2 is not None
        ):

            ax2.tick_params(
                axis="both",
                which="major",
                direction="in",
                labelsize=tick_fontsize,
                width=plot_def.get(
                    "tick_width",
                    1.0
                ),
                length=plot_def.get(
                    "tick_length",
                    2.5
                )
            )
            for label in ax2.get_yticklabels():
                label.set_fontweight(tick_fontweight)
        # --------------------------------------------------
        # Axis border / spine thickness
        # --------------------------------------------------

        spine_width = plot_def.get(
            "spine_width",
            2.5
        )

        for spine in ax.spines.values():
            spine.set_linewidth(
                spine_width
            )

        if ax2 is not None:

            for spine in ax2.spines.values():
                spine.set_linewidth(
                    spine_width
                )

        # --------------------------------------------------
        # Collect legend handles
        # --------------------------------------------------

        handles1, labels1 = (
            ax.get_legend_handles_labels()
        )

        if ax2 is not None:

            handles2, labels2 = (
                ax2.get_legend_handles_labels()
            )

        else:

            handles2, labels2 = [], []

        all_handles = (
            handles1 + handles2
        )

        all_labels = (
            labels1 + labels2
        )

        # --------------------------------------------------
        # Legend
        # --------------------------------------------------

        if not entry.get(
            "interval",
            False
        ):

            legend_linewidth = plot_def.get(
                "legend_linewidth",
                2
            )

            for handle in all_handles:

                try:
                    handle.set_linewidth(
                        legend_linewidth
                    )

                except AttributeError:
                    pass

            legend_kwargs = {

                # Remove box when False
                "frameon": plot_def.get(
                    "legend_frame",
                    False
                ),

                # Legend text size
                "fontsize": plot_def.get(
                    "legend_fontsize",
                    16
                ),

                # 1 = vertical
                "ncol": plot_def.get(
                    "legendCols",
                    1
                ),

                # Position
                "loc": plot_def.get(
                    "legendLocation",
                    "lower right"
                ),

                # Label first, line second
                "markerfirst": plot_def.get(
                    "markerfirst",
                    False
                ),

                # Legend line size
                "handlelength": plot_def.get(
                    "legend_handlelength",
                    1.2
                ),

                "handletextpad": plot_def.get(
                    "legend_handletextpad",
                    0.4
                ),

                "labelspacing": plot_def.get(
                    "legend_labelspacing",
                    0.3
                ),

                "borderpad": plot_def.get(
                    "legend_borderpad",
                    0.3
                ),
            }

            # Only use bbox if configured
            if plot_def.get(
                "bbox"
            ) is not None:

                legend_kwargs[
                    "bbox_to_anchor"
                ] = plot_def["bbox"]

            ax.legend(
                all_handles,
                all_labels,
                **legend_kwargs
            )

        else:

            ax.set_ylim(
                -0.5,
                len(all_labels) - 0.5
            )

            ax.get_xaxis().get_offset_text().set_visible(
                False
            )

            formatter = ticker.ScalarFormatter(
                useMathText=True
            )

            formatter.set_scientific(
                True
            )

            formatter.set_powerlimits(
                (6, 6)
            )

            ax.xaxis.set_major_formatter(
                formatter
            )

            ax.xaxis.get_major_formatter().set_useOffset(
                False
            )

        # --------------------------------------------------
        # Grid
        # --------------------------------------------------

        ax.grid(False)

        # --------------------------------------------------
        # Layout
        # --------------------------------------------------

        plt.tight_layout()

        # --------------------------------------------------
        # Output directory
        # --------------------------------------------------

        outDir = plot_dir

        output_name = plot_def.get(
            "label",
            f"plot_{plot_index}"
        )

        subDir = plot_def.get(
            "outputDir",
            None
        )

        if subDir:
            outDir = os.path.join(
                plot_dir,
                subDir
            )

        if not os.path.exists(outDir):
            os.makedirs(outDir)

        # --------------------------------------------------
        # SAVE PNG
        # --------------------------------------------------

        png_file = os.path.join(
            outDir,
            f"{output_name}.png"
        )

        plt.savefig(
            png_file,
            format="png",
            bbox_inches="tight",
            pad_inches=0.20,
            dpi=300
        )

        print(
            f"Saved: {output_name}.png"
        )

        # --------------------------------------------------
        # SAVE EPS
        # --------------------------------------------------

        eps_file = os.path.join(
            outDir,
            f"{output_name}.eps"
        )

        plt.savefig(
            eps_file,
            format="eps",
            bbox_inches="tight",
            pad_inches=0.20
        )

        print(
            f"Saved: {output_name}.eps"
        )

        # --------------------------------------------------
        # Close figure
        # --------------------------------------------------

        plt.close()

        plot_index += 1

        # --------------------------------------------------
        # Percentile plot
        # --------------------------------------------------

        if len(percentiles) != 0:

            percentile_file = os.path.join(
                outDir,
                f"{output_name}_percentile.png"
            )

            plot_percentile_bar(
                percentiles,
                percentile_file
            )

            print(
                f"Saved: "
                f"{output_name}_percentile.png"
            )

        # --------------------------------------------------
        # Generate CDF/PDF if requested
        # --------------------------------------------------

        if (
            plot_def.get(
                "probdist",
                False
            )
            and len(all_data) > 0
        ):

            try:

                plot_cdf(
                    np.array(all_data),
                    plot_def["y_label"],
                    os.path.join(
                        plot_dir,
                        f"{output_name}_cdf.png"
                    )
                )

            except Exception:
                print(
                    "CDF failed"
                )

            plot_pdf(
                np.array(all_data),
                plot_def["y_label"],
                os.path.join(
                    plot_dir,
                    f"{output_name}_pdf.png"
                )
            )
            
def choose_directory():
    root = tk.Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="Select parent directory containing the experiment")
    if not folder:
        print("No directory selected.")
        sys.exit(1)
    return folder

# === Setup and Run ===
if __name__ == "__main__":

    # Get parent_dir from CLI or prompt with GUI
    if len(sys.argv) > 1:
        parent_dir = sys.argv[1]
        if(len(sys.argv) > 2):
            scenerio = sys.argv[2]
    else:
        parent_dir = choose_directory()

    if not os.path.isdir(parent_dir):
        print(f"Error: Directory '{parent_dir}' does not exist.")
        sys.exit(1)


    print(f"Plotting in: {parent_dir}")

    # Loop through all subfolders
    for subfolder_name in sorted(os.listdir(parent_dir)):
        subfolder_path = os.path.join(parent_dir, subfolder_name)
        if not os.path.isdir(subfolder_path):
            continue

        print(f"\n==> Processing folder: {subfolder_name}")
        plot_dir = os.path.join(subfolder_path, "plots")
        os.makedirs(plot_dir, exist_ok=True)
        state_path = os.path.join(subfolder_path, "state.dat")
        regions = []
        # try:
        #     regions = load_state_regions(state_path)
        # except:
        #     pass

        # Decide which plot set to run
        if subfolder_name.lower() == "comparison":
            algos_to_compare = [
                #[("fqcodel", "FQ-CoDel"), ("fqcodelpp", "FQ-CoDel++")],
                [("fq_codel", "FQ-CoDel"), ("fq_codelpp", "FQ-CoDel++")],
                #[("fqpie", "FQ-PIE"), ("fqpieBulk", "FQ-PIE_NoBulkDrop")],
                #[("fq", "FQ-CoDel"), ("fqcodelpp", "FQ-CoDel++")],
                #[("fqcodel", "FQ-CoDel"), ("fqcodelnodb", "FQ-CoDel (No Drop batch)")],
                #[("fqpie", "FQ-PIE"), ("fqpienodb", "FQ-PIE (No Drop batch)")],
                # [("fqpie", "FQ-PIE"), ("fqpi2", "FQ-PI2")],
                # [("codel", "CoDel"), ("pie", "PIE")],
                # [("pi2", "PI2"), ("pie", "PIE")],
                #[("codel", "CoDel"), ("codelpp", "CoDel++")],
                # [("codel", "CoDel"), ("codelbql", "CoDel (BQL)")],
                # [("codelpp", "CoDel++"), ("codelppbql", "CoDel++ (BQL)")],
                # [("codel", "CoDel"), ("codelpp", "CoDel++"), ("codelbql", "CoDel (BQL)"), ("codelppbql", "CoDel++ (BQL)")],
                #[("fqcodel", "FQ-CoDel"), ("fqcodelpp", "FQ-CoDel++")],
                #[("cobalt", "COBALT"), ("codel", "CoDel"), ("codelpp", "CoDel++")],
                #[("pienodre", "PIE (Timestamp)"), ("piedre", "PIE (Little's law)")],
                #[("fqpienodre", "FQ-PIE (Timestamp)"), ("fqpiedre", "FQ-PIE (Little's law)")],
                # [("codel", "CoDel"), ("cobalt", "COBALT")],
                #[("cobalt", "COBALT"), ("cobaltnoblue", "COBALT (Without BLUE)")],
                #[("cobaltreset0", "COBALT Variant 1"), ("cobaltwait", "COBALT Variant 2")],
                #[("cobaltnoblue", "COBALT (Without BLUE)"), ("cobaltreset0", "COBALT Variant 1")],
                #[("cobaltnoblue", "COBALT (Without BLUE)"), ("cobaltwait", "COBALT Variant 2")],
                #[("cobaltnoblue", "COBALT (Without BLUE)"), ("codel", "CoDel")],
            ]
            plots_to_generate = [
                 {
                    "data": [
                        {"file": "pdrop_cobalt.dat", "label": "BLUE PDrop", "step" : True,},
                        {"file": "count_cobalt.dat", "label": "COBALT Count", "step" : True,},  
                    ],
                    "twoaxis": True,
                    "x_label": "Time (s)",
                    "y_label": ["Drop probability", "Count value"],
                    "title": f"BLUE Pdrop vs COBALT's CoDel Count value ({scenerio})",
                    "label" : "bluevscodel",
                    #"legendLocation": "lower center",
                    "bbox": (0.5, -0.30),
                    "legendCols": 2,
                    "legendLocation": "upper center",
                    "xlim": [0, 100],
                    #"state_overlay": True,
                    "cumulative": False,
                }
            ]
            for pdef in cmp_defs:
                plots_to_generate += generate_plot_definitions(algos_list=algos_to_compare,
                        file_prefix=pdef["fileprefix"],
                        interval=pdef.get("interval", False),
                        step=pdef.get("step", False),
                        title_template=pdef["title_template"],
                        label=pdef["label"],
                        params=pdef["plot_params"]
                    )
            # compare_flows(subfolder_path + "/fqqdelay_fqpie.dat",subfolder_path + "/fqqdelay_fqcodel.dat", plot_dir + "/fqqdelay.png")
            # compare_flows(subfolder_path + "/fqpdrop_fqpie.dat",subfolder_path + "/fqpdrop_fqcodel.dat", plot_dir + "/fqpdrop.png")

            pdef = algos_to_compare[0]
           # plot_ellipses_from_qdelay_throughput(
           #     base_dir=subfolder_path,
           #     algos=[pdef[0][0], pdef[0][0], pdef[2][0], pdef[3][0]],
           #     labels=[pdef[0][1], pdef[1][1], pdef[2][1], pdef[3][1]],
           #     output_path=os.path.join(plot_dir, "codel_fqcodel_fqpie_pie","ellipses.png"),
           #     nstd=1.0
           # )
            #plot_qdelay_boxplot(
            #    base_dir=subfolder_path, 
            #    algos=[pdef[0][0], pdef[0][0], pdef[2][0], pdef[3][0]],
            #    labels=[pdef[0][1], pdef[1][1], pdef[2][1], pdef[3][1]],
            #    output_path=os.path.join(plot_dir, "codel_fqcodel_fqpie_pie" ,f"boxplot_cmp_codel_fqcodel_fqpie_pie.png"))
          #  continue
            # compare_flows(subfolder_path + "/fqcount_fqcodel.dat",subfolder_path + "/fqcount_fqcodelnodb.dat", plot_dir + "/fqcount_codel.png", None, "Count Value", ("FQ-CoDel","FQ-CoDel (No Drop Batch)"), "Per Flow Count Value")
            # compare_flows(subfolder_path + "/fqqdelay_fqcodel.dat",subfolder_path + "/fqqdelay_fqcodelnodb.dat", plot_dir + "/fqqdelay_codel.png", None, "Queue Delay (ms)", ("FQ-CoDel", "FQ-CoDel (No Drop Batch)"))
            # compare_flows(subfolder_path + "/fqpdrop_fqpie.dat",subfolder_path + "/fqpdrop_fqpienodb.dat", plot_dir + "/fqpdrop_fqpie.png", None, "PDrop", ("FQ-PIE","FQ-PIE (No Drop Batch)"), "Per Flow Pdrop Value")
            # compare_flows(subfolder_path + "/fqqdelay_fqpie.dat",subfolder_path + "/fqqdelay_fqpienodb.dat", plot_dir + "/fqqdelay_fqpie.png", None, "Queue Delay (ms)", ("FQ-PIE", "FQ-PIE (No Drop Batch)"))
        else:      
            continue  
            plots_to_generate = single_plots
            
        generate_plots(subfolder_path, plot_dir, plots_to_generate, regions)
