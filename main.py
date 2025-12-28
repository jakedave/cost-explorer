import argparse
import json

from datetime import datetime, timedelta

import boto3

client = boto3.client("ce")

FILTER = {
    "And": [
        {
            "Not": {
                "Dimensions": {
                    "Key": "RECORD_TYPE",
                    "Values": ["Support", "Tax"],
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


def main(end_date):
    start_date = end_date - timedelta(days=7)
    start_date_last_week = start_date - timedelta(days=7)

    filtered_total_cost = get_total_cost(
        get_cost_and_usage(start_date, end_date, FILTER)
    )

    unfiltered_total_cost = get_total_cost(get_cost_and_usage(start_date, end_date))

    filtered_total_cost_last_week = get_total_cost(
        get_cost_and_usage(start_date_last_week, start_date, FILTER)
    )

    unfiltered_total_cost_last_week = get_total_cost(
        get_cost_and_usage(start_date_last_week, start_date)
    )

    filtered_cost_by_service = get_total_groups_cost(
        get_cost_and_usage(
            start_date,
            end_date,
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
            start_date_last_week,
            start_date,
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
        ## TODO: do i really need to check this? new aws services?
        if k in filtered_cost_by_service_last_week
    }

    difference_by_service_sorted = {
        k: v
        for k, v in sorted(
            difference_by_service.items(), key=lambda item: item[1], reverse=True
        )
    }

    print(
        f"Total cost from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} with exclusions: ${filtered_total_cost:,.2f}"
    )
    print(
        f"Total cost from {start_date_last_week.strftime('%Y-%m-%d')} to {start_date.strftime('%Y-%m-%d')} with exclusions: ${filtered_total_cost_last_week:,.2f}\n"
    )
    print(
        f"Total cost from {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} without exclusions: ${unfiltered_total_cost:,.2f}"
    )
    print(
        f"Total cost from {start_date_last_week.strftime('%Y-%m-%d')} to {start_date.strftime('%Y-%m-%d')} without exclusions: ${unfiltered_total_cost_last_week:,.2f}\n"
    )

    print(
        f"Difference between weeks with exclusions: ${filtered_total_cost - filtered_total_cost_last_week:,.2f}"
    )
    print(
        f"Difference between weeks without exclusions: ${unfiltered_total_cost - unfiltered_total_cost_last_week:,.2f}\n"
    )

    print("Difference between weeks by service with exclusions:\n")
    for service, cost in difference_by_service_sorted.items():
        print(
            f"{service.removeprefix('AWS').removeprefix('Amazon').lstrip()}: ${cost:,.2f}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d"),
        default=datetime.today(),
    )

    main(parser.parse_args().end_date)
