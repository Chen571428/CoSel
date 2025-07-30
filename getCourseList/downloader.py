import functools as ft
import logging
import os
import random
import re
import time
from argparse import ArgumentParser
from collections import namedtuple
from multiprocessing import Pool

import bs4
import pandas as pd
import requests
from rich.logging import RichHandler
from tqdm import tqdm

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
    "Origin": "https://dean.pku.edu.cn",
    "Referer": "https://dean.pku.edu.cn/service/web/courseSearch.php",
    "Content-Type": "application/x-www-form-urlencoded",
}
data = Query("", "", "24-25-2", "0", "0")
HTML_tag_pattern = re.compile("<.*?>")
request_url = "https://dean.pku.edu.cn/service/web/courseSearch_do.php"
base_url = "https://dean.pku.edu.cn/service/web/courseSearch.php"
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


def getVerificationCode(session):
    """Download verification code image and prompt user to input"""
    global logger
    try:
        response = session.get("https://dean.pku.edu.cn/service/web/course_vercode.php", headers=getHeaders())
        if response.status_code == 200:
            # Save the verification code image
            with open("vercode.png", "wb") as f:
                f.write(response.content)
            logger.info("Verification code image saved as 'vercode.png'")
            logger.info("Please open 'vercode.png' and enter the verification code:")
            vercode = input("Verification code: ").strip()
            return vercode
        else:
            logger.error(f"Failed to get verification code: {response.status_code}")
            return ""
    except Exception as e:
        logger.error(f"Error getting verification code: {str(e)}")
        return ""


def createSession():
    """Create a session and get initial cookies"""
    session = requests.Session()
    try:
        # Visit the main page to get session cookies
        response = session.get(base_url, headers=getHeaders())
        if response.status_code == 200:
            logger.debug("Session created successfully")
            return session
        else:
            logger.error(f"Failed to create session: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        return None


def _post(query: Query, startrow: str = "0", session=None, vercode=""):
    global logger
    logger.debug(f"POST {request_url} with {query._asdict() | {'startrow': startrow}}")
    
    if session is None:
        session = requests.Session()
    
    # Add verification code to the data
    post_data = query._asdict() | {"startrow": startrow, "vercode": vercode}
    
    return session.post(
        request_url, headers=getHeaders(), data=post_data
    )


def getCourseListPart(query: Query, startrow: str, retry: int, session=None, vercode=""):
    """Get a part of the course list, 10 rows per request"""

    global logger
    response = _post(query, startrow, session, vercode)

    # Loop to re-attempt if the server does not return a 200 status code
    while response.status_code != 200 and retry > 0:
        logger.warning(
            f"Got status code {response.status_code} from server, retrying {retry} times left..."
        )
        response = _post(query, startrow, session, vercode)
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
    except Exception as e:
        logger.error(
            f"Failed to parse JSON from seg {int(startrow) // 10}: {str(e)}"
        )
        logger.error(f"Response content: {response.text[:200]}...")
        return None

    # Check if the response indicates verification code error
    if "courselist" not in json:
        logger.error(f"No courselist in response, might need verification code")
        logger.error(f"Response: {json}")
        return None

    # Create dataframe, apply stripping of HTML tags and set index as '序号'
    df = pd.DataFrame(json["courselist"]).map(stripHTMLtags)
    df.columns = colnames
    df.set_index("序号", inplace=True)

    # Log success information
    logger.debug(f"Successfully got course list row {startrow}-{int(startrow)+9}")
    return df


def getTotalCount(query: Query, retry: int, session=None, vercode=""):
    """Get the total number of courses matching the query"""

    global logger
    response = _post(query, "0", session, vercode)

    # Loop to re-attempt if the server does not return a 200 status code
    while response.status_code != 200 and retry > 0:
        logger.warning(
            f"Got status code {response.status_code} from server, retrying {retry} times left..."
        )
        response = _post(query, "0", session, vercode)
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
    except Exception as e:
        logger.error(f"Failed to parse JSON: {str(e)}")
        logger.error(f"Response content: {response.text[:200]}...")
        return None

    # Check if count is in the response
    if "count" not in json:
        logger.error(f"No count in response, might need verification code")
        logger.error(f"Response: {json}")
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

    # Create session and get verification code
    session = createSession()
    if session is None:
        logger.critical("Failed to create session, aborting...")
        return None
    
    vercode = getVerificationCode(session)
    if not vercode:
        logger.warning("No verification code provided, trying without it...")

    # Get the total number of matching courses
    total_count = getTotalCount(query, retry, session, vercode)
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
    
    # Estimate time based on typical request speed (approximately 0.5-1 second per request)
    estimated_time = len(segs) * 0.75  # seconds
    if estimated_time > 60:
        logger.info(f"Estimated time: {estimated_time/60:.1f} minutes")
    else:
        logger.info(f"Estimated time: {estimated_time:.0f} seconds")

    # Record start time for actual time tracking
    start_time = time.time()
    
    # Iterate over each segment and try to retrieve the courses with progress bar
    if parallel:
        # Note: parallel processing with sessions is complex, using sequential for now
        logger.warning("Parallel processing not supported with verification codes, using sequential...")
        result = []
        with tqdm(total=len(segs), desc="Fetching course data", unit="segment") as pbar:
            for seg in segs:
                segment_result = getCourseListPart(query, str(seg), retry, session, vercode)
                result.append(segment_result)
                pbar.update(1)
                
                # Update ETA based on actual progress
                elapsed = time.time() - start_time
                if pbar.n > 0:
                    avg_time_per_segment = elapsed / pbar.n
                    remaining_segments = len(segs) - pbar.n
                    eta_seconds = remaining_segments * avg_time_per_segment
                    if eta_seconds > 60:
                        pbar.set_postfix(ETA=f"{eta_seconds/60:.1f}min")
                    else:
                        pbar.set_postfix(ETA=f"{eta_seconds:.0f}s")
    else:
        # use good old for loop with progress bar
        result = []
        with tqdm(total=len(segs), desc="Fetching course data", unit="segment") as pbar:
            for seg in segs:
                segment_result = getCourseListPart(query, str(seg), retry, session, vercode)
                result.append(segment_result)
                pbar.update(1)
                
                # Update ETA based on actual progress
                elapsed = time.time() - start_time
                if pbar.n > 0:
                    avg_time_per_segment = elapsed / pbar.n
                    remaining_segments = len(segs) - pbar.n
                    eta_seconds = remaining_segments * avg_time_per_segment
                    if eta_seconds > 60:
                        pbar.set_postfix(ETA=f"{eta_seconds/60:.1f}min")
                    else:
                        pbar.set_postfix(ETA=f"{eta_seconds:.0f}s")

    # Calculate and display total time taken
    total_time = time.time() - start_time
    if total_time > 60:
        logger.info(f"Total time taken: {total_time/60:.1f} minutes")
    else:
        logger.info(f"Total time taken: {total_time:.0f} seconds")

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
        default=2,
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
    argparser.add_argument(
        "-v",
        "--vercode",
        help="Verification code (if not provided, will prompt for input)",
        type=str,
        default=""
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
