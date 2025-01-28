import functools as ft
import logging
import os
import random
import re
from argparse import ArgumentParser
from collections import namedtuple
from multiprocessing import Pool

import bs4
import pandas as pd
import requests
from rich.logging import RichHandler

Query = namedtuple(
    "Query", ["coursename", "teachername", "yearandseme", "coursetype", "yuanxi"]
)

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 Edg/89.0.774.63",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 Edg/89.0.774.63",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 OPR/75.0.3969.267",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 OPR/75.0.3969.267",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 Vivaldi/3.8.2259.37",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 Vivaldi/3.8.2259.37",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 Firefox/87.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36 Firefox/87.0",
]

headers = {
    "Origin": "http://www.dean.pku.edu.cn",
    "Referer": "http://www.dean.pku.edu.cn/service/web/courseSearch.php",
    "Content-Type": "application/x-www-form-urlencoded",
}
data = Query("", "", "24-25-2", "0", "0")
HTML_tag_pattern = re.compile("<.*?>")
request_url = "http://www.dean.pku.edu.cn/service/web/courseSearch_do.php"
base_url = "http://www.dean.pku.edu.cn/service/web/courseSearch.php"
colnames = [
    "序号",
    "课程号",
    "课程名称",
    "课程类型",
    "开课单位",
    "班号",
    "学分",
    "执行计划编号",
    "起止周",
    "上课时间",
    "教师",
    "备注",
]
logger = logging.getLogger()
logger.addHandler(RichHandler())


def getHeaders():
    global headers
    return headers | {"User-Agent": random.choice(user_agents)}


def query2str(query: Query):
    return f"CN{query.coursename}_TN{query.teachername}_YS{query.yearandseme}_CT{query.coursetype}_YX{query.yuanxi}"


def stripHTMLtags(text):
    if not isinstance(text, str):
        return text
    return re.sub(HTML_tag_pattern, "", text)


def _post(query: Query, startrow: str = "0"):
    global logger
    logger.debug(f"POST {request_url} with {query._asdict() | {'startrow': startrow}}")
    return requests.post(
        request_url, headers=getHeaders(), data=query._asdict() | {"startrow": startrow}
    )


def getCourseListPart(query: Query, startrow: str, retry: int):
    """Get a part of the course list, 10 rows per request"""

    global logger
    response = _post(query, startrow)

    # Loop to re-attempt if the server does not return a 200 status code
    while response.status_code != 200 and retry > 0:
        logger.warning(
            f"Got status code {response.status_code} from server, retrying {retry} times left..."
        )
        response = _post(query, startrow)
        retry -= 1

    # Return error message if the request fails after having retried
    if response.status_code != 200:
        logger.error(
            f"Failed to get response, server returned {response.status_code}: {response.text}, aborting..."
        )
        return None

    # Try to parse data into a json object
    try:
        json = response.json()
    except Exception:
        logger.error(
            f"Failed to parse JSON from seg {int(startrow) // 10}, aborting..."
        )
        return None

    # Create dataframe, apply stripping of HTML tags and set index as '序号'
    df = pd.DataFrame(json["courselist"]).applymap(stripHTMLtags)
    df.columns = colnames
    df.set_index("序号", inplace=True)

    # Log success information
    logger.debug(f"Successfully got course list row {startrow}-{int(startrow)+9}")
    return df


def getTotalCount(query: Query, retry: int):
    """Get the total number of courses matching the query"""

    global logger
    response = _post(query)

    # Loop to re-attempt if the server does not return a 200 status code
    while response.status_code != 200 and retry > 0:
        logger.warning(
            f"Got status code {response.status_code} from server, retrying {retry} times left..."
        )
        response = _post(query)
        retry -= 1

    # Return error message if the request fails after having retried
    if response.status_code != 200:
        logger.error(
            f"Failed to get response, server returned {response.status_code}: {response.text}, aborting..."
        )
        return None

    # Try to parse data into a json object
    try:
        json = response.json()
    except Exception:
        logger.error(f"Failed to parse JSON, aborting...")
        return None

    # Log success information
    logger.info(f"Successfully got course count {int(json['count'])}")
    return int(json["count"])


def getOptions(retry: int):
    """Get the available course type and school/department options"""

    global logger
    logger.debug(f"GET {base_url}")
    response = requests.get(base_url, headers=getHeaders())

    # Loop to re-attempt if the server does not return a 200 status code
    while response.status_code != 200 and retry > 0:
        logger.warning(
            f"Got status code {response.status_code} from server, retrying {retry} times left..."
        )
        response = requests.get(base_url, headers=getHeaders())
        retry -= 1

    # Return error message if the request fails after having retried
    if response.status_code != 200:
        logger.critical(f"Failed to get options, aborting...")
        return None

    # Parse HTML and extract options
    html = response.text
    soup = bs4.BeautifulSoup(html, "html.parser")
    yuanxi: dict[str, str] = {
        item["data"]: item.text
        for item in soup.find_all("span", {"class": "yuanxi"}, recursive=True)
    }
    coursetype: dict[str, str] = {
        item["data"]: item.text
        for item in soup.find_all("span", {"class": "coursetype"}, recursive=True)
    }
    return yuanxi, coursetype


def getCourseList(query: Query = data, retry: int = 3, parallel: bool = False):
    """Retrieve a complete list of courses matching the provided query."""

    global logger

    # Get the total number of matching courses
    total_count = getTotalCount(query, retry)
    if total_count is None:
        logger.critical(f"Failed to get total count, aborting...")
        return None

    # Check if any matching results were found
    if total_count == 0:
        logger.info(f"Got 0 matching result, aborting...")
        return None

    # Get the course list in segments of 10 rows
    segs = list(range(0, total_count, 10))
    logger.info(f"Got {total_count} courses, {len(segs)} segments to fetch")

    # Iterate over each segment and try to retrieve the courses
    if parallel:
        # use a multiprocessing pool to speed up
        pool = Pool()
        result = pool.map(
            ft.partial(getCourseListPart, query, retry=retry), map(str, segs)
        )
    else:
        # use good old for loop
        result = [getCourseListPart(query, str(seg), retry) for seg in segs]

    # Check if there are any failed requests left
    failed = [idx * 10 for idx, item in enumerate(result) if item is None]
    if len(failed):
        logging.error(f"Failed to fetch {len(failed)} segments: {failed}")
    else:
        logger.info(f"Successfully fetched all segments")

    # Concatenate the result into a single DataFrame and return
    return pd.concat([item for item in result if item is not None])


def isValidQuery(query: Query, retry: int):
    """Check if the query is valid"""

    # Check on the validity of the coursetype and yuanxi field
    options = getOptions(retry)
    if options is None:
        logger.critical("Failed to get options")
        return False
    yuanxi, coursetype = options
    if query.yuanxi not in yuanxi.keys():
        logger.critical("Valid yuanxi values and meanings are:")
        for k, v in yuanxi.items():
            logger.critical(f"{k}: {v}")
        logger.critical(f"But got invalid yuanxi code: {query.yuanxi}")
        return False
    if query.coursetype not in coursetype.keys():
        logger.critical("Valid coursetype values and meanings are:")
        for k, v in coursetype.items():
            logger.critical(f"{k}: {v}")
        logger.critical(f"But got invalid coursetype code: {query.coursetype}")
        return False

    # Check on the validity of the yearandseme field
    year_s, year_e, semester = map(int, query.yearandseme.split("-"))
    if year_e != year_s + 1 or semester < 1 or semester > 3:
        logger.critical(f"Invalid yearandseme: {query.yearandseme}")
        logger.critical(
            f"Did you mean {min(year_s, year_e)}-{min(year_s, year_e) + 1}-{min(max(semester, 1), 3)}?"
        )
        return False
    return True


def main():
    global logger

    # Parse input arguments
    argparser = ArgumentParser()
    argparser.add_argument(
        "-c",
        "--coursename",
        help="Course name to look up for (default empty string for all)",
        type=str,
        default="",
    )
    argparser.add_argument(
        "-t",
        "--teachername",
        help="Teacher name to look up for (default empty string for all)",
        type=str,
        default="",
    )
    argparser.add_argument(
        "-s",
        "--coursetype",
        help="Course type to look up for (default 0 for all)",
        type=str,
        default="0",
    )
    argparser.add_argument(
        "-y",
        "--yuanxi",
        help="School/department to look up for (this is the code for school/department, default 0 for all)",
        type=str,
        default="0",
    )
    argparser.add_argument(
        "-r",
        "--retry",
        help="Max number of retries before giving up (default 3)",
        type=int,
        default=3,
    )
    argparser.add_argument(
        "-l",
        "--loglevel",
        help="Log level for printing to console (default 2:INFO)",
        type=int,
        default=0,
    )
    argparser.add_argument(
        "-p",
        "--parallel",
        help="Enable multi-processing scraping (default False)",
        action="store_true",
    )
    argparser.add_argument(
        "-f",
        "--force",
        help="Overwrite the existing output file (default False)",
        action="store_true",
    )
    argparser.add_argument(
        "-ys",
        help="Year and semester to look up for (e.g. 22-23-1 stands for the first semester in year 2022-2023)",
        type=str,
        default="24-25-2"
    )
    args = argparser.parse_args()
    logger.setLevel(args.loglevel * 10)

    # Setting up query parameters and do some checks
    query = Query(
        args.coursename,
        args.teachername,
        args.ys,
        args.coursetype,
        args.yuanxi,
    )
    logger.info(f"Querying {query2str(query)}")
    if not isValidQuery(query, args.retry):
        logger.critical(f"Encountered invalid query parameters, aborting...")
        return

    # Check if output file exists
    if os.path.exists(f"{query2str(query)}.csv") and not args.force:
        logger.info(
            f"File {query2str(query)}.csv already exists, use -f to force overwrite"
        )
        return

    # Fetch and save
    df = getCourseList(query, args.retry, args.parallel)
    if df is not None:
        df.sort_values(by="序号").to_csv(f"{query2str(query)}.csv", encoding="utf-8-sig")
        logger.info(f"Job finished, saved to {query2str(query)}.csv")


if __name__ == "__main__":
    main()