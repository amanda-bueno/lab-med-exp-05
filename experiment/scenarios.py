from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    name: str
    graphql_query: str


def build_scenarios(user_id: int, page: int, limit: int) -> list[Scenario]:
    return [
        Scenario(
            "simple_user",
            f"""
            query {{
              user(id: {user_id}) {{
                id
                name
                email
              }}
            }}
            """,
        ),
        Scenario(
            "user_list",
            f"""
            query {{
              users(page: {page}, limit: {limit}) {{
                id
                name
                city
              }}
            }}
            """,
        ),
        Scenario(
            "nested_data",
            f"""
            query {{
              user(id: {user_id}) {{
                id
                name
                posts {{
                  id
                  title
                  comments {{
                    id
                    text
                  }}
                }}
              }}
            }}
            """,
        ),
        Scenario(
            "post_titles",
            f"""
            query {{
              user(id: {user_id}) {{
                id
                posts {{
                  title
                }}
              }}
            }}
            """,
        ),
        Scenario(
            "full_profile",
            f"""
            query {{
              user(id: {user_id}) {{
                id
                name
                email
                phone
                city
                posts {{
                  id
                  title
                  body
                  authorId
                  comments {{
                    id
                    text
                    postId
                    authorId
                  }}
                }}
              }}
            }}
            """,
        ),
    ]
