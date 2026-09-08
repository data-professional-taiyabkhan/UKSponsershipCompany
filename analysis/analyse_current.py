import pandas as pd
D='/mnt/user-data/uploads/UK Sponsership/data/'

def load(f, sheet, valcol):
    raw = pd.read_excel(D+f, sheet_name=sheet, header=None, nrows=12)
    hdr = [i for i in range(12) if str(raw.iloc[i,0]).strip()=='Year'][0]
    d = pd.read_excel(D+f, sheet_name=sheet, header=hdr)
    d = d[d['Year'].notna()].copy()
    d[valcol]=pd.to_numeric(d[valcol],errors='coerce').fillna(0)
    d['Year']=d['Year'].astype(int)
    return d

print("="*72); print("ENTRY CLEARANCE GRANTS — YE June 2026 release"); print("="*72)
g = load('occupation-soc2020-visas-datasets-jun-2026.xlsx','Data_Occ_D02','Grants')
g.to_csv('grants26.csv',index=False)
sk = g[g['Visa type subgroup'].isin(['Skilled Worker','Health and Care Worker'])]
piv = sk.pivot_table(index='Year',columns='Visa type subgroup',values='Grants',aggfunc='sum').fillna(0)
piv['Total']=piv.sum(axis=1)
print(piv.astype(int).to_string())
print("\nQuarterly (SW + H&C):")
qq = sk.groupby('Quarter')['Grants'].sum().astype(int)
print(qq.tail(10).to_string())

print("\n--- Rolling 12m to Q2 2026 vs Q2 2023 peak ---")
q = sk.groupby('Quarter')['Grants'].sum().sort_index()
r12 = q.rolling(4).sum()
print(r12.dropna().astype(int).tail(14).to_string())

print("\n--- IT professionals (SOC 213) by year ---")
it = sk[sk['Occ. minor group'].astype(str).str.startswith('213')]
print(it.groupby('Year')['Grants'].sum().astype(int).to_string())
print("\n--- IT professionals, quarterly, last 8 ---")
print(it.groupby('Quarter')['Grants'].sum().astype(int).tail(8).to_string())

print("\n--- 2026 H1 top occupation minor groups ---")
o = sk[sk['Year']==2026].groupby('Occ. minor group')['Grants'].sum().sort_values(ascending=False)
print(o.head(12).astype(int).to_string())

print("\n--- Industry: 2023 vs YE-Q2-2026 ---")
last4 = ['2025 Q3','2025 Q4','2026 Q1','2026 Q2']
a = sk[sk['Year']==2023].groupby('Industry')['Grants'].sum()
b = sk[sk['Quarter'].isin(last4)].groupby('Industry')['Grants'].sum()
c = pd.DataFrame({'2023':a,'YE Q2-2026':b}).fillna(0).astype(int)
c['chg%'] = ((c['YE Q2-2026']/c['2023'].replace(0,pd.NA))-1)*100
print(c.sort_values('2023',ascending=False).head(12).round(0).to_string())

print("\n"+"="*72); print("IN-COUNTRY (extensions) — YE June 2026"); print("="*72)
e = load('extensions-datasets-jun-2026.xlsx','Data_Exe_D01','Decisions')
m = e[(e['Case outcome']=='Granted') & (e['Applicant type']=='Main Applicant')]
for sub in ['Skilled Worker','Health and Care Worker','Graduate']:
    s = m[m['Category of leave subgroup']==sub]
    if len(s): print(f'\n{sub} (in-country grants, main applicants):'); print(s[s['Year']>=2022].groupby('Year')['Decisions'].sum().astype(int).to_string())

print("\n--- SWITCHING INTO Skilled Worker (Exe_D02) ---")
raw = pd.read_excel(D+'extensions-datasets-jun-2026.xlsx', sheet_name='Data_Exe_D02', header=None, nrows=5)
hdr=[i for i in range(5) if str(raw.iloc[i,0]).strip()=='Year'][0]
s2 = pd.read_excel(D+'extensions-datasets-jun-2026.xlsx', sheet_name='Data_Exe_D02', header=hdr)
s2 = s2[s2['Year'].notna()].copy()
s2.columns=[str(c).replace('\n','').strip() for c in s2.columns]
s2['Grants']=pd.to_numeric(s2['Grants'],errors='coerce').fillna(0); s2['Year']=s2['Year'].astype(int)
s2.to_csv('switch26.csv',index=False)
cur='Current category of leave'; prev='Previous category of leave'
sw = s2[s2[cur].astype(str).str.contains('Skilled Worker',na=False)]
p = sw.pivot_table(index=prev,columns='Year',values='Grants',aggfunc='sum').fillna(0).astype(int)
p = p[[c for c in p.columns if c>=2022]]
print(p.loc[p.sum(axis=1).sort_values(ascending=False).index].head(8).to_string())
newin = sw[~sw[prev].isin(['Worker','Temporary worker'])]
print('\nNEW entrants switching INTO SW from inside UK:')
print(newin[newin['Year']>=2022].groupby('Year')['Grants'].sum().astype(int).to_string())
