import boto3

import json
from datetime import datetime, timedelta

client = boto3.client("ce")

FILTER = {
    "And": [
        {
            "Not": {
                "Dimensions": {
                    "Key": "RECORD_TYPE",
                    "Values": ["Support Fee", "Tax"],
                    "MatchOptions": ["EQUALS"],
                }
            },
        },
        {
            "Not": {
                "Dimensions": {
                    "Key": "SERVICE",
                    "Values": ["Advanced Reserved Instances Automation"],
                    "MatchOptions": ["EQUALS"],
                },
            }
        },
        {
            "Not": {
                "Dimensions": {
                    "Key": "PURCHASE_TYPE",
                    "Values": ["Reserved"],
                    "MatchOptions": ["EQUALS"],
                }
            }
        },
    ]
}


def get_cost_and_usage(start_date, end_date, filter=None, group_by=None):
    kwargs = {
        "TimePeriod": {
            # inclusive
            "Start": start_date.strftime("%Y-%m-%d"),
            # exclusive
            "End": end_date.strftime("%Y-%m-%d"),
        },
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
    }
    if filter:
        kwargs["Filter"] = filter
    if group_by:
        kwargs["GroupBy"] = group_by
    return client.get_cost_and_usage(**kwargs)


def get_total_cost(response, metric="UnblendedCost"):
    total_cost = 0
    for result in response.get("ResultsByTime"):
        total_cost += float(result["Total"][metric]["Amount"])
    return round(total_cost, 2)


def get_total_groups_cost(response, metric="UnblendedCost"):
    cost_by_group = {}
    for result in response.get("ResultsByTime"):
        for group in result["Groups"]:
            if group["Keys"][0] not in cost_by_group:
                cost_by_group[group["Keys"][0]] = 0
            cost_by_group[group["Keys"][0]] += float(group["Metrics"][metric]["Amount"])
    return {k: round(v, 2) for k, v in cost_by_group.items()}


CURRENT_WEEK_START = datetime.today() - timedelta(days=7)
CURRENT_WEEK_END = datetime.today()

LAST_WEEK_START = CURRENT_WEEK_START - timedelta(days=7)


if __name__ == "__main__":
    filtered_total_cost = get_total_cost(
        get_cost_and_usage(CURRENT_WEEK_START, CURRENT_WEEK_END, FILTER)
    )

    unfiltered_total_cost = get_total_cost(
        get_cost_and_usage(CURRENT_WEEK_START, CURRENT_WEEK_END)
    )

    filtered_total_cost_last_week = get_total_cost(
        get_cost_and_usage(LAST_WEEK_START, CURRENT_WEEK_START, FILTER)
    )

    unfiltered_total_cost_last_week = get_total_cost(
        get_cost_and_usage(LAST_WEEK_START, CURRENT_WEEK_START)
    )

    print(
        f"Total cost from {CURRENT_WEEK_START.strftime('%Y-%m-%d')} to {CURRENT_WEEK_END.strftime('%Y-%m-%d')} with exclusions: ${filtered_total_cost:,.2f}"
    )
    print(
        f"Total cost from {LAST_WEEK_START.strftime('%Y-%m-%d')} to {CURRENT_WEEK_START.strftime('%Y-%m-%d')} with exclusions: ${filtered_total_cost_last_week:,.2f}\n"
    )
    print(
        f"Total cost from {CURRENT_WEEK_START.strftime('%Y-%m-%d')} to {CURRENT_WEEK_END.strftime('%Y-%m-%d')} without exclusions: ${unfiltered_total_cost:,.2f}"
    )
    print(
        f"Total cost from {LAST_WEEK_START.strftime('%Y-%m-%d')} to {CURRENT_WEEK_START.strftime('%Y-%m-%d')} without exclusions: ${unfiltered_total_cost_last_week:,.2f}\n"
    )

    print(
        f"Difference between weeks with exclusions: ${filtered_total_cost - filtered_total_cost_last_week:,.2f}"
    )
    print(
        f"Difference between weeks without exclusions: ${unfiltered_total_cost - unfiltered_total_cost_last_week:,.2f}\n"
    )

    filtered_cost_by_service = get_total_groups_cost(
        get_cost_and_usage(
            CURRENT_WEEK_START,
            CURRENT_WEEK_END,
            filter=FILTER,
            group_by=[
                {
                    "Type": "DIMENSION",
                    "Key": "SERVICE",
                }
            ],
        )
    )

    filtered_cost_by_service_last_week = get_total_groups_cost(
        get_cost_and_usage(
            LAST_WEEK_START,
            CURRENT_WEEK_START,
            filter=FILTER,
            group_by=[
                {
                    "Type": "DIMENSION",
                    "Key": "SERVICE",
                }
            ],
        )
    )

    difference_by_service = {
        k: filtered_cost_by_service[k] - filtered_cost_by_service_last_week[k]
        for k in filtered_cost_by_service.keys()
        ## TODO: do i really need to check this?
        if k in filtered_cost_by_service_last_week
    }

    difference_by_service_sorted = {
        k: v
        for k, v in sorted(
            difference_by_service.items(), key=lambda item: item[1], reverse=True
        )
    }

    print("Difference between weeks by service with exclusions:\n")
    for service, cost in difference_by_service_sorted.items():
        print(
            f"{service.removeprefix('AWS').removeprefix('Amazon').lstrip()}: ${cost:,.2f}"
        )
