import csv

csv_file = open("missing.csv", "r")
csv_reader = csv.reader(csv_file, delimiter=",")
print(csv_reader)

