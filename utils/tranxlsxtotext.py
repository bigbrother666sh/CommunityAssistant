import xlrd

data = xlrd.open_workbook('raw.xlsx')
table = data.sheets()[0]

with open("target.txt", 'w', encoding='utf-8') as f:
    for i in range(2, table.nrows):
        for j in range(2, table.ncols):
            f.write(table.cell_value(i, j))
            f.write('\n')
