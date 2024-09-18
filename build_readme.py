from python_graphql_client import GraphqlClient
import httpx
import json
import pathlib
import re
import os

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
GRAPHQL_REPO_QUERY = """
query {
  search(first: 100, type:REPOSITORY, query:"is:public owner:alibekbirlikbai sort:updated", after: AFTER) {
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
        repos = data["data"]["search"]["nodes"]
        for repo in repos:
            repo_name = repo["name"]

            # Skip excluded repositories
            if repo_name in EXCLUDED_REPOS:
                continue

            # Iterate over all branches (refs)
            for ref in repo.get("refs", {}).get("nodes", []):
                for commit in ref.get("target", {}).get("history", {}).get("nodes", []):
                    author = commit.get("author")
                    if author is not None:
                        user = author.get("user")
                        if user is not None:
                            login = user.get("login")
                            if login != "readme-bot":
                                commits.append(
                                    {
                                        "repo": repo_name,
                                        "message": commit.get("message", "No message"),
                                        "date": commit.get("committedDate", "No date").split("T")[0],
                                        "url": commit.get("url", "No URL"),
                                        "sha": commit.get("oid", "No SHA"),
                                    }
                                )
        has_next_page = data["data"]["search"]["pageInfo"]["hasNextPage"]
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]
    return commits

def fetch_pull_requests(oauth_token):
    pull_requests = []
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

            for pr in repo.get("pullRequests", {}).get("nodes", []):
                pull_requests.append(
                    {
                        "title": pr["title"],
                        "url": pr["url"],
                        "created_at": pr["createdAt"].split("T")[0],
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
                        "repo": repo["name"],
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
            "- [{} - {}](https://github.com/{}/commit/{}) - {}".format(
                commit["repo"],
                commit["message"],
                commit["repo"],
                commit["sha"],
                commit["date"].split("T")[0],
            )
            for commit in commits[:10]
        ]
    )

    pull_requests_md = "\n\n".join(
        [
            "- [{}]({}) - {}".format(
                pr["title"],
                pr["url"],
                pr["created_at"]
            )
            for pr in pull_requests
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
            for release in releases[:8]
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
                commit["url"],
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
                pr["title"],
                pr["url"],
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
