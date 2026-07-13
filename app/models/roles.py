from enum import Enum


class OrganizationRole(str, Enum):
    ADMIN = "ADMIN"
    MANAGER = "MANAGER"
    AGENT = "AGENT"
    REQUESTER = "REQUESTER"
