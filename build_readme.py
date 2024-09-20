from python_graphql_client import GraphqlClient
import httpx
import json
import pathlib
import re
import os
import requests
from datetime import datetime

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("REPO_TOKEN", "")

EXCLUDED_REPOS = [
    "jwt-basic",
    "django-backend",
    "news-api",
    "spring-backend",
]

GRAPHQL_REPO_QUERY = """
query {
  search(first: 100, type: REPOSITORY, query: "is:public owner:alibekbirlikbai sort:updated", after: AFTER) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      __typename
      ... on Repository {
        name
        url
        pullRequests(first: 100, states: [OPEN, MERGED], orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            title
            url
            state
            updatedAt
            createdAt
            # closedAt
            merged
            mergedAt
            author {
              login
            }
            commits {
              totalCount
            }
          }
        }
        refs(first: 100, refPrefix: "refs/heads/") {
          nodes {
            name
            target {
              ... on Commit {
                history(first: 1) {  # Get latest commit for current branch
                  totalCount
                  nodes {
                    message
                    committedDate
                    url
                    author {
                      user {
                        login
                      }
                    }
                    oid
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

total_pull_requests = 0
repo_with_pull_requests = set()
repo_with_commits = set()

def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
        r"<!-- {} starts -->.*<!-- {} ends -->".format(marker, marker),
        re.DOTALL,
    )
    if not inline:
        chunk = "\n{}\n".format(chunk)
    chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)

def make_query(after_cursor=None):
    return GRAPHQL_REPO_QUERY.replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    )

def fetch_pull_requests(oauth_token):
    global total_pull_requests
    pull_requests = []
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )

        if "data" not in data:
            print("Error fetching data: ", data)
            break

        repos = data["data"]["search"]["nodes"]
        for repo in repos:
            repo_name = repo["name"]
            repo_url = repo["url"]

            if repo_name in EXCLUDED_REPOS:
                continue

            repo_has_valid_pr = False  # Flag to check if repo has any non-closed PRs

            # Fetch pull requests
            for pr in repo.get("pullRequests", {}).get("nodes", []):
                pr_status = "merged" if pr.get("merged") else pr.get("state", "Unknown").lower()

                if pr_status != "closed":
                    total_pull_requests += 1
                    repo_has_valid_pr = True

                    # Use mergedAt if the PR is merged, otherwise use updatedAt
                    last_updated = pr.get("mergedAt") if pr.get("merged") else pr.get("updatedAt")

                    # Get the total count of commits
                    pr_commits_count = pr.get("commits", {}).get("totalCount", 0)

                    pull_requests.append({
                        "repo_name": repo_name,
                        "repo_url": repo_url,
                        "pr_title": pr.get("title", "No title"),
                        "pr_url": pr.get("url", "No URL"),
                        "pr_status": pr_status,
                        "updated_at": last_updated.split("T")[0],
                        "created_at": pr.get("createdAt", "Unknown").split("T")[0],
                        "pr_commits_count": pr_commits_count,
                    })

            # Add repo to set only if it has any non-closed PRs
            if repo_has_valid_pr:
                repo_with_pull_requests.add(repo_name)

        has_next_page = data["data"]["search"]["pageInfo"]["hasNextPage"]
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]

    return pull_requests

def fetch_commits(oauth_token):
    commits = []
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
        if "data" not in data:
            print("Error fetching data: ", data)
            break

        repos = data["data"]["search"]["nodes"]
        for repo in repos:
            repo_name = repo["name"]
            repo_url = repo["url"]  # Get the repo URL

            if repo_name in EXCLUDED_REPOS:
                continue

            repo_with_commits.add(repo_name)

            all_commits = []
            # Iterate over all branches (refs)
            for ref in repo.get("refs", {}).get("nodes", []):
                # Get total count for the current branch
                branch_commits_count = ref.get("target", {}).get("history", {}).get("totalCount", 0)

                for commit in ref.get("target", {}).get("history", {}).get("nodes", []):
                    author = commit.get("author")
                    if author is not None:
                        user = author.get("user")
                        if user is not None:
                            login = user.get("login")
                            if login != "readme-bot":
                                all_commits.append(
                                    {
                                        "repo_name": repo_name,
                                        "repo_url": repo_url,
                                        "branch_commits_count": branch_commits_count,  # Add branch commit count here
                                        "message": commit.get("message", "No message"),
                                        "date": commit.get("committedDate", "No date").split("T")[0],
                                        "commit_url": commit.get("url", "No URL"),
                                        "sha": commit.get("oid", "No SHA"),
                                    }
                                )

            # Select the latest commit from all branches
            if all_commits:
                latest_commit = max(all_commits, key=lambda x: x["date"])
                commits.append(latest_commit)

        has_next_page = data["data"]["search"]["pageInfo"]["hasNextPage"]
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]

    return commits

def fetch_releases(oauth_token):
    releases = []
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
        repos = data["data"]["search"]["nodes"]
        for repo in repos:
            repo_name = repo["name"]

            # Skip excluded repositories
            if repo_name in EXCLUDED_REPOS:
                continue

            # Check if the 'releases' field exists
            if "releases" in repo and repo["releases"]["totalCount"] > 0:
                releases.append(
                    {
                        "repo_name": repo["name"],
                        "repo_url": repo["url"],
                        "release": repo["releases"]["nodes"][0]["name"]
                        .replace(repo["name"], "")
                        .strip(),
                        "published_at": repo["releases"]["nodes"][0]["publishedAt"],
                        "published_day": repo["releases"]["nodes"][0][
                            "publishedAt"
                        ].split("T")[0],
                        "url": repo["releases"]["nodes"][0]["url"],
                    }
                )
        has_next_page = data["data"]["search"]["pageInfo"]["hasNextPage"]
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]
    return releases

if __name__ == "__main__":
    readme = root / "README.md"
    commits_file = root / "md" / "commits.md"
    pull_requests_file = root / "md" / "pull_requests.md"
    releases_file = root / "md" / "releases.md"

    commits = fetch_commits(TOKEN)
    pull_requests = fetch_pull_requests(TOKEN)
    releases = fetch_releases(TOKEN)

    status_signs = {
        "open": ":white_check_mark:",
        # "closed": ":x:",
        "merged": ":ballot_box_with_check:"
    }

    pull_requests_md = "\n\n".join(
        [
            "- [_{}_]({}) - (_{}_ commits total)<br/>"
            "pr: [{}]({}) - {} _{}_ - _{}_".format(
                pr["repo_name"],
                pr["repo_url"],
                pr["pr_commits_count"],
                pr["pr_title"],
                pr["pr_url"],
                status_signs.get(pr["pr_status"], "Unknown status"),
                pr["pr_status"],
                pr["updated_at"],
            )
            for pr in pull_requests[:5]
        ]
    )

    commits_md = "\n\n".join(
        [
            "- [_{}_]({}) - (_{}_ commits total)<br/>"
            "commit: [{}]({}) - _{}_".format(
                commit["repo_name"],
                commit["repo_url"],
                commit["branch_commits_count"],
                commit["message"],
                commit["commit_url"],
                commit["date"].split("T")[0],
            )
            for commit in commits[:5]
        ]
    )

    releases_md = "\n\n".join(
        [
            "- [{} - {}]({}) - {}".format(
                release["repo"],
                release["release"],
                release["url"],
                release["published_day"]
            )
            for release in releases[:5]
        ]
    )

    readme_contents = readme.open().read()
    readme_contents = replace_chunk(readme_contents, "recent_commits", commits_md)
    readme_contents = replace_chunk(readme_contents, "recent_pull_requests", pull_requests_md)
    readme_contents = replace_chunk(readme_contents, "recent_releases", releases_md)

    readme_contents = replace_chunk(
        readme_contents,
        "pull_requests_count",
        "`" + str(total_pull_requests) + "`",
        inline=True,
    )
    readme_contents = replace_chunk(
        readme_contents,
        "project_with_pull_requests_count",
        "`" + str(len(repo_with_pull_requests)) + "`",
        inline=True,
    )
    readme_contents = replace_chunk(
        readme_contents,
        "project_count",
        "`" + str(len(repo_with_commits)) + "`",
        inline=True,
    )

    readme.open("w").write(readme_contents)

    # Write out commits.md
    commits_md_full = "\n".join(
        [
            "- [_{}_]({}) - (_{}_ commits total)<br/>"
            "commit: [{}]({}) - _{}_".format(
                commit["repo_name"],
                commit["repo_url"],
                commit["branch_commits_count"],
                commit["message"],
                commit["commit_url"],
                commit["date"].split("T")[0],
            )
            for commit in commits
        ]
    )
    commits_file.open("w").write(commits_md_full)

    # Write out pull_requests.md
    pull_requests_md_full = "\n".join(
        [
            "- [_{}_]({}) - (_{}_ commits total)<br/>"
            "pr: [{}]({}) - {} _{}_ - _{}_".format(
                pr["repo_name"],
                pr["repo_url"],
                pr["pr_commits_count"],
                pr["pr_title"],
                pr["pr_url"],
                status_signs.get(pr["pr_status"], "Unknown status"),
                pr["pr_status"],
                pr["updated_at"],
            )
            for pr in pull_requests
        ]
    )
    pull_requests_file.open("w").write(pull_requests_md_full)

    # Write out releases.md
    releases_md_full = "\n".join(
        [
            "* **[{}]({})**: [{}]({}) - {}".format(
                release["repo"],
                release["repo_url"],
                release["release"],
                release["url"],
                release["published_day"],
            )
            for release in releases
        ]
    )
    releases_file.open("w").write(releases_md_full)
