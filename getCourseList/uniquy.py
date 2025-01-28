import csv

input_file = 'CN_TN_YS24-25-2_CT0_YX0.csv'
output_file = 'unique_courses.csv'
class Uniqunizer:
    def __init__(self, input_file, output_file):
        self.input_file = input_file
        self.output_file = output_file
    def unique(self):
    # 使用集合来存储唯一的课程号
        unique_courses = set()
        unique_coursesList = list()
        # 读取 CSV 文件并去重
        with open(input_file, mode='r', encoding='utf-8') as infile:
            reader = csv.reader(infile)
            header = next(reader)  # 读取表头
            for row in reader:
                course_id = str(row[1]) + str(row[5]) + str(row[7]) + str(row[10]) # 假设课程号在第一列
                if course_id not in unique_courses:
                    unique_courses.add(course_id)
                    unique_coursesList.append(row)
        # 将去重后的数据写入新的 CSV 文件
        with open(output_file, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.writer(outfile)
            writer.writerow(header)  # 写入表头
            for course in unique_coursesList:
                writer.writerow(course)
        
