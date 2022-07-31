import xlrd
from pprint import pprint

data = xlrd.open_workbook('./data/courses.xlsx')
table = data.sheets()[0]

courses = {}
nrows = table.nrows
if nrows < 2:
    print('no data in courses.xls,this is not allowed')
    exit(1)
for i in range(1, nrows):
    courses[table.cell_value(i, 0)] = {'pre_prompt': table.cell_value(i, 2), 'des': f'情景对话模拟训练已开始。\n{table.cell_value(i, 1)}', 'opening': table.cell_value(i, 3)}

pprint(courses)
for title in courses.keys():
    print(title)
    print(type(title))
