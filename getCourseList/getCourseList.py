import subprocess,os
from uniquy import Uniqunizer
if __name__ == '__main__':
    subprocess.run(['conda','run','-n','cosel','python','downloader.py'])
    Uniqunizer = Uniqunizer('CN_TN_YS25-26-1_CT0_YX0.csv','unique_courses.csv')
    Uniqunizer.unique()