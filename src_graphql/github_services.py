"""Github related commands and functions."""

from datetime import datetime, timedelta, timezone
from collections import defaultdict
import logging
import requests
from dateutil import parser
from src_graphql.github_domain import PullRequest


_TOKEN = None
GITHUB_GRAPHQL_URL = 'https://api.github.com/graphql'
PULL_REQUESTS_URL_TEMPLATE = 'https://api.github.com/repos/{0}/{1}/pulls'
ISSUE_TIMELINE_URL_TEMPLATE = (
    'https://api.github.com/repos/{0}/{1}/issues/{2}/timeline')
CREATE_DISCUSSION_URL_TEMPLATE = (
    'https://api.github.com/orgs/{0}/teams/{1}/discussions')

def init_service(token=None):
    """Intialize service with the given token."""
    if token is None:
        raise Exception('Must provide Github Personal Access Token.')

    global _TOKEN # pylint: disable=global-statement
    _TOKEN = token

def check_token(func):
    """A decorator to check whether the service is intialized with the token."""
    def execute_if_token_initialized(*args, **kwargs):
        """Executes the given function if the token is intialized."""
        if _TOKEN is None:
            raise Exception(
                'Intialize the service with '
                'gtihub_services.init_service(TOKEN).')
        return func(*args, **kwargs)

    return execute_if_token_initialized

def _get_request_headers():
    """Retunrs the request hearders for github-request."""
    return {
        'Accept': 'application/vnd.github.v3+json',
        'Authorization': 'token {0}'.format(_TOKEN)
    }

@check_token
def get_prs_assigned_to_reviewers(org_name, repository, wait_hours):
    """Fetchs all the PRs on the given repository and retuens a list of PRs
    assigned to reviewers.
    """
    pr_url = PULL_REQUESTS_URL_TEMPLATE.format(org_name, repository)

    reviewer_to_assigned_prs = defaultdict(list)

    page_number = 1
    while True:
        logging.info('Fetching Pull requests')
        response = requests.get(
            pr_url,
            params={'page': page_number, 'per_page': 100, 'status': 'open'},
            headers=_get_request_headers()
        )
        response.raise_for_status()
        pr_subset = response.json()

        if len(pr_subset) == 0:
            break
        page_number += 1


        pull_requests = [
            PullRequest.from_github_response(pull_request)
            for pull_request in pr_subset]
        update_assignee_timestamp(org_name, repository, pull_requests)
        for pull_request in pull_requests:
            if not pull_request.is_reviewer_assigned():
                continue
            for reviewer in pull_request.assignees:
                pending_review_time = (
                    datetime.now(timezone.utc) - reviewer.timestamp)
                if (reviewer.name != pull_request.author) and (
                        pending_review_time >= timedelta(hours=wait_hours)):
                    reviewer_to_assigned_prs[reviewer.name].append(pull_request)
    return reviewer_to_assigned_prs

def __process_activity(pull_request, event):
    """Process activity and updates assignee timestamps."""
    if event['event'] != 'assigned':
        return

    assignee = pull_request.get_assignee(event['assignee']['login'])
    event_timestamp = parser.parse(event['created_at'])
    if assignee:
        assignee.set_timestamp(max([assignee.timestamp, event_timestamp]))


def update_assignee_timestamp(org_name, repository, pr_list):
    """Fetchs PR timeline and updates assignment timestamp."""
    for pull_request in pr_list:
        pr_number = pull_request.number
        activity_url = ISSUE_TIMELINE_URL_TEMPLATE.format(
            org_name, repository, pr_number)

        page_number = 1
        while True:
            logging.info('Fetching PR #%s timeline', pr_number)
            response = requests.get(
                activity_url,
                params={'page': page_number, 'per_page': 100},
                headers={
                    'Accept': 'application/vnd.github.mockingbird-preview+json',
                    'Authorization': 'token {0}'.format(_TOKEN)}
            )
            response.raise_for_status()
            timeline_subset = response.json()

            if len(timeline_subset) == 0:
                break

            for event in timeline_subset:
                __process_activity(pull_request, event)

            page_number += 1


@check_token
def create_discussion_comment(org_name, repo, body):
    """Creates github discussion on the team_slug with the given title and
    body.
    """

    query_category_id = """
        query($org_name: String!, $repository: String!) {
            repository(owner: $org_name, name: $repository) {
                discussionCategories(first: 10) {
                    nodes {
                        id
                        name
                    }
                }
            }
        }
    """

    variables = {
        "org_name": org_name,
        "repository": repo
    }

    response = requests.post(
        GITHUB_GRAPHQL_URL, json={'query': query_category_id, 'variables': variables}, headers=_get_request_headers()
    )

    data = response.json()
    print("request made successfuly")
    print(data)

    # Check for a category with the name. If it exists, use that category id
    category_id = (category['id'] for category in data['data']['repository']['discussionCategories']['nodes'] if category['name'] == 'Reviewer notifications')


    query_discussion_id = """
    {
        query ($org_name: String!, $repository: String!, $category_id: ID!) {
            repository(owner: $org_name, name: $repository) {
                discussions(categoryId: $category_id, first: 10) {
                    edges{
                        node {
                            id
                            title
                        }
                    }
                }
            }
        }
    }
    """

    variables = {
        "org_name": org_name,
        "repository": repo,
        "category_id": category_id
    }

    response = requests.post(
        GITHUB_GRAPHQL_URL, json={'query': query_discussion_id, 'variables': variables}, headers=_get_request_headers()
    )

    data = response.json()
    # Assuming the particular category will have only one discussion
    discussion_id = data['data']['repository']['discussions']['edges'][0]['node']['id']
    # discussion_id = data['data']['repository']['discussions']['edges'][0]['node']['id'] if data['data']['repository']['discussions']['edges'][0]['node']['title'] == "Pending Reviews" else None

    comment_in_discussion = """
    {
        mutation comment($discussion_id: ID!, $comment: String!) {
            addDiscussionComment(input: {discussionId: $discussion_id, body: $comment}) {
                clientMutationId
                comment {
                    id
                }
            }
        }
    }
    """

    variables = {
        "discussion_id": discussion_id,
        "comment": body
    }

    response = requests.post(
        GITHUB_GRAPHQL_URL, json={'query': comment_in_discussion, 'variables': variables}, headers=_get_request_headers()
    )

    response.raise_for_status()