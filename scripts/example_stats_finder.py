# This python script is an example of how we take metadata extracted 
# from the github repo to locate ADF diagnostics and read the data 
# from the generated CSV
from pathlib import Path

import pandas as pd

# parameters
#-----------
# typically these parameter would be 'discovered'
# and used as input arguments
simulation_run_by_user = "hannay"

casename = "b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.301"

adf_location = Path(f"/glade/derecho/scratch/{simulation_run_y_user}/ADF")
#-----------
# derive additiona information
adf_plots = adf_location / casename / "plots"

# when we find CSV files, here's what we expect for the structure:
# Expected columns
expected_columns = ["variable", "unit", "mean", "sample size", "standard dev.", "standard error", "95% CI", "trend", "trend p-value"]


# there could be multiple time spans
# with diagnostics as subdirecties under 'plots'
adf_plot_time_intervals = adf_plots.glob("*")

# if len(adf_plot_time_intervals) > 1 then we need
# some way to select which to use (or use all of them as separate entries)
# for this example, just take last one:
adf_plot_time_interval = adf_plot_time_intervals[-1]

# Similar to time spans, there can be multiple diagnostic
# sets under the time span, these can be either:
# (1) model-vs-model as [casename]_[casetimespan]_vs_[refcase]_[reftimespan]
# (2) model-vs-observations as [casename]_[casetimespan]_vs_Obs

adf_diagnostic_sets = adf_plot_time_interval.glob("*")

adf_diagnostic_set = adf_diagnostic_sets[-1]

# Within the diagnostic set, sometimes there will be "website"
# and other times there will be all the plots and files
# For this example, assume we find plots and files,
# look for csv files
csv_files = adf_diagnostic_set.glob("*.csv")

# When the diagnostics are model-vs-model, there will
# be CSV files for both cases, but when it is model-vs-Obs
# there should only be CSV files for one case.
# Typically there will be one with annual mean statistics.

if len(csv_files) > 1:
    # Find the file that contains the casename
    matching_file = next((f for f in csv_files if casename in str(f)), None)
    if matching_file:
        df = pd.read_csv(matching_file)
        print(df)
    else:
        print(f"No file found containing '{casename}'")

    # Check if the columns match
    if list(df.columns) == expected_columns:
        print("Columns match expected format")
    else:
        print("Warning: Columns don't match expected format")
        print(f"Expected: {expected_columns}")
        print(f"Got: {list(df.columns)}")

    # Count the number of variables (rows in the dataframe)
    num_variables = len(df)
    print(f"Number of variables: {num_variables}")