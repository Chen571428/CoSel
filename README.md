# PKU | CoSel

北京大学预科生/旁听生辅助选课工具

## 功能特性
- 全校课程数据爬取与更新
- 可视化课程时间表展示
- 智能选课冲突检测
- 学分统计与进度追踪
- 课表导出功能（支持iCalendar格式）
- 自定义课程筛选与收藏

## 技术栈
- 前端：Vue2 + Vuetify + FullCalendar
- 后端：Python + BeautifulSoup
- 数据存储：CSV文件

## 快速开始
```bash
# 安装Python依赖
pip install -r getCourseList/requirements.txt

# 更新课程数据
cd getCourseList
python getCourseList.py

# 启动本地服务（前端）
cd ..
python -m http.server 8000
```

## 项目结构
```
CoSel/
├── index.html                 # 主界面
├── getCourseList/             # 课程爬取模块
│   ├── getCourseList.py       # 主爬取脚本
│   ├── downloader.py          # 文件下载器
│   ├── uniquy.py             # 课程去重脚本
│   ├── remove_duplicates.py   # 重复课程清理脚本
│   └── requirements.txt       # Python依赖
└── CourseListTemplates/       # 课程模板文件
```

## 免责声明
本项目仅供学习研究使用，开发者不对以下内容负责：
1. 课程信息的及时性和准确性
2. 使用本工具造成的任何教务系统访问异常
3. 因依赖版本差异导致的程序运行问题
4. 任何因课程选择不当导致的学业问题
5. 系统兼容性问题（推荐使用最新版Chrome浏览器）

### 使用规范
- 禁止高频访问教务系统（建议每日更新不超过2次）
- 不得将本项目用于商业用途
- 请遵守北京大学计算机使用管理规定

建议使用者定期通过[教务部官网](https://dean.pku.edu.cn)核实课程信息

## 许可证
本项目采用 [MIT License](LICENSE) 开源协议
