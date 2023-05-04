"""Domain objects for github entities."""

from datetime import datetime, timezone, MINYEAR

DEFAULT_TIMESTAMP = datetime(MINYEAR, 1, 1, tzinfo=timezone.utc)

class Assignee:
    """A class representing a assignee of a pull request."""
    def __init__(self, name, timestamp=DEFAULT_TIMESTAMP):
        self.name = name
        self.timestamp = timestamp

    def set_timestamp(self, timestamp):
        """Sets timestamp to assignee."""
        self.timestamp = timestamp

    def get_readable_waiting_time(self):
        """"Returns redable wating time on review."""
        delta = datetime.now(timezone.utc) - self.timestamp
        days = delta.days
        hours, _ = divmod(delta.seconds, 3600)
        waiting_time = []
        if days:
            waiting_time.append('{0} day{1}'.format(
                days, 's' if days > 1 else ''))

        if hours:
            waiting_time.append('{0} hour{1}'.format(
                hours, 's' if hours > 1 else ''))

        return ', '.join(waiting_time)

    def __repr__(self):
        return '@{0} assigned on {1}'.format(self.name, self.timestamp)

class PullRequest:
    """A class representing a pull request on github."""
    def __init__(self, url, number, author, title, assignees):
        self.url = url
        self.number = number
        self.title = title
        self.author = author
        self.assignees = assignees

    def is_reviewer_assigned(self):
        """Checks whether a reviewer assigned to the PR."""
        return not (
            len(self.assignees) == 1 and self.assignees[0].name == self.author)

    def get_assignee(self, user):
        """Retuns the assignee object for the given user if exist."""
        return next(filter(lambda x: x.name == user, self.assignees), None)

    def __repr__(self):
        return 'PR #{0} by {1}'.format(self.number, self.author)

    @classmethod
    def from_github_response(cls, pr_dict):
        """Created the object using the github pull_request response."""
        assignees_dict = pr_dict['assignees']
        assignees = [Assignee(a['login']) for a in assignees_dict]

        pull_request = cls(
            url=pr_dict['html_url'],
            number=pr_dict['number'],
            title=pr_dict['title'],
            author=pr_dict['user']['login'],
            assignees=assignees
        )
        return pull_request
