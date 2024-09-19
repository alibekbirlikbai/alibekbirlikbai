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

# List of repositories to exclude from tracking
EXCLUDED_REPOS = [
    "full-stack",
    "social-network-django",
    "news-api",
    "ticket-booking-service",
]

# Define GraphQL queries
GRAPHQL_QUERY = """
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
        refs(first: 100, refPrefix: "refs/heads/") {  # Fetch all branches
          nodes {
            name  # Branch name
            target {
              ... on Commit {
                history(first: 1) {  # Get the latest commit for this branch
                  nodes {
                    message
                    committedDate
                    url
                    author {
                      user {
                        login
                      }
                    }
                    oid  # Use oid for commit SHA
                  }
                }
              }
            }
          }
        }
        pullRequests(first: 100, states: [OPEN, CLOSED], after: AFTER_PR) {  # Fetch pull requests
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            title
            url
            state
            updatedAt
          }
        }
      }
    }
  }
}
"""

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
            repo_url = repo["url"]  # Add this line to get the repo URL

            # Skip excluded repositories
            if repo_name in EXCLUDED_REPOS:
                continue

            all_commits = []
            # Iterate over all branches (refs)
            for ref in repo.get("refs", {}).get("nodes", []):
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
                                        "repo_url": repo_url,  # Add this line to include the repo URL
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

def fetch_pull_requests(oauth_token):
    pull_requests = []
    has_next_page = True
    after_cursor = None

    while has_next_page:
        query = GRAPHQL_PULL_REQUEST_QUERY.replace(
            "REPO_NAME", "owner:alibekbirlikbai sort:updated"  # Modify this according to your needs
        ).replace(
            "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
        )

        data = client.execute(
            query=query,
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )

        if "data" not in data:
            print("Error fetching data: ", data)
            break

        prs = data["data"]["search"]["nodes"]
        for pr in prs:
            repo_name = pr["url"].split("/")[4]  # Extract repo name from URL

            # Skip excluded repositories
            if repo_name in EXCLUDED_REPOS:
                continue

            pull_requests.append(
                {
                    "repo": repo_name,
                    "repo_url": pr["url"],
                    "pr_title": pr["title"],
                    "pr_url": pr["url"],
                    "pr_status": pr["state"],
                    "updated_at": pr["updatedAt"].split("T")[0],
                }
            )

        has_next_page = data["data"]["search"]["pageInfo"]["hasNextPage"]
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]

    return pull_requests

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

    commits_md = "\n\n".join(
        [
            "- [{}]({}) - [{}]({}) - {}".format(
                commit["repo_name"],
                commit["repo_url"],
                commit["message"],
                commit["commit_url"],
                commit["date"].split("T")[0],
            )
            for commit in commits[:10]
        ]
    )

    pull_requests_md = "\n\n".join(
        [
            "- [{}]({}) - [{}]({}) - {} - {}".format(
                pr["repo"],
                pr["repo_url"],
                pr["pr_title"],
                pr["pr_url"],
                pr["pr_status"],
                pr["updated_at"]
            )
            for pr in pull_requests[:10]
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
            for release in releases[:10]
        ]
    )

    readme_contents = readme.open().read()
    readme_contents = replace_chunk(readme_contents, "recent_commits", commits_md)
    readme_contents = replace_chunk(readme_contents, "recent_pull_requests", pull_requests_md)
    readme_contents = replace_chunk(readme_contents, "recent_releases", releases_md)

    readme.open("w").write(readme_contents)

    # Write out commits.md
    commits_md_full = "\n".join(
        [
            "* **[{}]({})** - {}: {}".format(
                commit["message"],
                commit["commit_url"],
                commit["date"],
                commit["sha"],
            )
            for commit in commits
        ]
    )
    commits_file.open("w").write(commits_md_full)

    # Write out pull_requests.md
    pull_requests_md_full = "\n".join(
        [
            "* **[{}]({})** - {}".format(
                pr["pr_title"],
                pr["pr_title"],
                pr["created_at"],
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
