from python_graphql_client import GraphqlClient
import json
import pathlib
import re
import os

root = pathlib.Path(__file__).parent.resolve()
client = GraphqlClient(endpoint="https://api.github.com/graphql")

TOKEN = os.environ.get("REPO_TOKEN", "")

def replace_chunk(content, marker, chunk, inline=False):
    r = re.compile(
        r"<!\-\- {} starts \-\->.*<!\-\- {} ends \-\->".format(marker, marker),
        re.DOTALL,
    )
    if not inline:
        chunk = "\n{}\n".format(chunk)
    chunk = "<!-- {} starts -->{}<!-- {} ends -->".format(marker, chunk, marker)
    return r.sub(chunk, content)

GRAPHQL_SEARCH_QUERY = """
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
        description
        url
        releases(orderBy: {field: CREATED_AT, direction: DESC}, first: 1) {
          totalCount
          nodes {
            name
            publishedAt
            url
          }
        }
      }
    }
  }
}
"""

def make_query(after_cursor=None):
    return GRAPHQL_SEARCH_QUERY.replace(
        "AFTER", '"{}"'.format(after_cursor) if after_cursor else "null"
    )

def fetch_releases(oauth_token):
    repos = []
    releases = []
    has_next_page = True
    after_cursor = None

    while has_next_page:
        data = client.execute(
            query=make_query(after_cursor),
            headers={"Authorization": "Bearer {}".format(oauth_token)},
        )
        repo_nodes = data["data"]["search"]["nodes"]
        for repo in repo_nodes:
            if repo["releases"]["totalCount"]:
                repos.append(repo)
                releases.append(
                    {
                        "repo": repo["name"],
                        "repo_url": repo["url"],
                        "description": repo["description"],
                        "release": repo["releases"]["nodes"][0]["name"]
                        .replace(repo["name"], "")
                        .strip(),
                        "published_at": repo["releases"]["nodes"][0]["publishedAt"],
                        "published_day": repo["releases"]["nodes"][0][
                            "publishedAt"
                        ].split("T")[0],
                        "url": repo["releases"]["nodes"][0]["url"],
                        "total_releases": repo["releases"]["totalCount"],
                    }
                )
        after_cursor = data["data"]["search"]["pageInfo"]["endCursor"]
        has_next_page = after_cursor
    return releases

if __name__ == "__main__":
    readme = root / "README.md"
    releases = fetch_releases(TOKEN)
    releases.sort(key=lambda r: r["published_at"], reverse=True)
    md = "\n\n".join(
        [
            "[{repo} {release}]({url}) - {published_day}".format(**release)
            for release in releases[:8]
        ]
    )
    readme_contents = readme.open().read()
    rewritten = replace_chunk(readme_contents, "recent_releases", md)
    readme.open("w").write(rewritten)
