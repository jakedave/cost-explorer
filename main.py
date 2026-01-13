import argparse
import json

from datetime import datetime, date, timedelta

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


def get_cost_and_usage(
    start_date, end_date, filter=None, group_by=None, granularity="DAILY"
):
    kwargs = {
        "TimePeriod": {
            # inclusive
            "Start": start_date.strftime("%Y-%m-%d"),
            # exclusive
            "End": end_date.strftime("%Y-%m-%d"),
        },
        "Granularity": granularity,
        "Metrics": ["UnblendedCost"],
    }
    if filter:
        kwargs["Filter"] = filter
    if group_by:
        kwargs["GroupBy"] = group_by
    return client.get_cost_and_usage(**kwargs)


def get_total_cost(response):
    total_cost = 0
    for result in response["ResultsByTime"]:
        total_cost += float(result["Total"]["UnblendedCost"]["Amount"])
    return round(total_cost, 2)


def get_total_groups_cost(response):
    cost_by_group = {}
    for result in response["ResultsByTime"]:
        for group in result["Groups"]:
            group_key = group["Keys"][0]
            if group_key not in cost_by_group:
                cost_by_group[group_key] = 0

            cost_by_group[group_key] += float(
                group["Metrics"]["UnblendedCost"]["Amount"]
            )
    return {k: round(v, 2) for k, v in cost_by_group.items()}


def get_dict_difference(d1, d2):
    return {
        k: d1.get(k, 0) - d2.get(k, 0) for k in set(d1.keys()).union(set(d2.keys()))
    }


def main(end_date):
    start_date = end_date - timedelta(days=7)
    start_date_last_week = start_date - timedelta(days=7)

    first_day_of_year = date(end_date.year, 1, 1)
    last_day_of_year = date(end_date.year, 12, 31)

    weeks_left_in_year = round(
        (last_day_of_year - (end_date - timedelta(days=1))).days / 7, 2
    )

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
        k: v
        for k, v in sorted(
            get_dict_difference(
                filtered_cost_by_service, filtered_cost_by_service_last_week
            ).items(),
            key=lambda i: i[1],
            reverse=True,
        )
    }

    ytd_unfiltered_cost = get_total_cost(
        get_cost_and_usage(first_day_of_year, end_date, granularity="MONTHLY")
    )

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
    for service, cost in difference_by_service.items():
        print(
            f"{service.removeprefix('AWS').removeprefix('Amazon').lstrip()}: ${cost:,.2f}"
        )

    print(f"\nCurrent YTD cost: ${ytd_unfiltered_cost:,.2f}")
    print(
        f"Estimated year-end cost with {weeks_left_in_year} weeks left in year based on current week's cost with exclusions: ${ytd_unfiltered_cost + (weeks_left_in_year * filtered_total_cost):,.2f}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
    )

    main(parser.parse_args().end_date)
