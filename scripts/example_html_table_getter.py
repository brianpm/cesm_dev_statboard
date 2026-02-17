import pandas as pd

url = "https://webext.cgd.ucar.edu/BLT1850/b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302/atm/b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302_2_20_vs_b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.299_2_20/html_table/amwg_table_b.e30_alpha08b.B1850C_LTso.ne30_t232_wgx3.302.html"

# read_html returns a list of all tables found on the page
tables = pd.read_html(url)

# The data you want is likely in the second or third table
# Based on the page structure, the main AMWG table is usually tables[1]
df = tables[1]

print(df.head())