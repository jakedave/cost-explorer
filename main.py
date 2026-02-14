import argparse
import json
import math

from datetime import datetime, date, timedelta

import boto3

client = boto3.client("ce")

DIMENSION_RECORD_TYPE = {
    "Dimensions": {
        "Key": "RECORD_TYPE",
        "Values": ["Support", "Tax"],
        "MatchOptions": ["EQUALS"],
    }
}

DIMENSION_SERVICE = {
    "Dimensions": {
        "Key": "SERVICE",
        "Values": ["Advanced Reserved Instances Automation"],
        "MatchOptions": ["EQUALS"],
    }
}

DIMENSION_PURCHASE_TYPE = {
    "Dimensions": {
        "Key": "PURCHASE_TYPE",
        "Values": ["Reserved"],
        "MatchOptions": ["EQUALS"],
    }
}

EXCLUSIONS_FILTER = {
    "And": [
        {
            "Not": DIMENSION_RECORD_TYPE,
        },
        {
            "Not": DIMENSION_SERVICE,
        },
        {
            "Not": DIMENSION_PURCHASE_TYPE,
        },
    ]
}

INVERSE_EXCLUSIONS_FILTER = {
    "Or": [DIMENSION_RECORD_TYPE, DIMENSION_SERVICE, DIMENSION_PURCHASE_TYPE]
}


def get_cost_and_usage(
    start_date, end_date, filter=None, group_by=None, granularity="DAILY"
):
    kwargs = {
        "TimePeriod": {
            ## inclusive
            "Start": start_date.strftime("%Y-%m-%d"),
            ## exclusive
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

    end_date_exclusive = end_date - timedelta(days=1)
    start_date_exclusive = start_date - timedelta(days=1)

    first_day_of_year = date(end_date_exclusive.year, 1, 1)
    last_day_of_year = date(end_date_exclusive.year, 12, 31)

    first_day_of_month = date(end_date_exclusive.year, end_date_exclusive.month, 1)

    ## end date is exclusive in cost calc
    monthes_left_in_year = 12 - end_date_exclusive.month + 1

    weeks_left_in_year = math.ceil((last_day_of_year - end_date_exclusive).days / 7)

    filtered_total_cost = get_total_cost(
        get_cost_and_usage(start_date, end_date, EXCLUSIONS_FILTER)
    )

    unfiltered_total_cost = get_total_cost(get_cost_and_usage(start_date, end_date))

    filtered_total_cost_last_week = get_total_cost(
        get_cost_and_usage(start_date_last_week, start_date, EXCLUSIONS_FILTER)
    )

    unfiltered_total_cost_last_week = get_total_cost(
        get_cost_and_usage(start_date_last_week, start_date)
    )

    filtered_cost_by_service = get_total_groups_cost(
        get_cost_and_usage(
            start_date,
            end_date,
            filter=EXCLUSIONS_FILTER,
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
            filter=EXCLUSIONS_FILTER,
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

    ## technically the same as mtd unfiltered - mtd filtered but requires one less api call
    mtd_inverse_filtered_cost = get_total_cost(
        get_cost_and_usage(
            first_day_of_month,
            end_date,
            filter=INVERSE_EXCLUSIONS_FILTER,
            granularity="MONTHLY",
        )
    )

    print(
        f"Total cost from {start_date.strftime('%Y-%m-%d')} to {end_date_exclusive.strftime('%Y-%m-%d')} with exclusions: ${filtered_total_cost:,.2f}"
    )
    print(
        f"Total cost from {start_date_last_week.strftime('%Y-%m-%d')} to {start_date_exclusive.strftime('%Y-%m-%d')} with exclusions: ${filtered_total_cost_last_week:,.2f}\n"
    )
    print(
        f"Total cost from {start_date.strftime('%Y-%m-%d')} to {end_date_exclusive.strftime('%Y-%m-%d')} without exclusions: ${unfiltered_total_cost:,.2f}"
    )
    print(
        f"Total cost from {start_date_last_week.strftime('%Y-%m-%d')} to {start_date_exclusive.strftime('%Y-%m-%d')} without exclusions: ${unfiltered_total_cost_last_week:,.2f}\n"
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
    print(f"Current MTD inverse exclusions cost: ${mtd_inverse_filtered_cost:,.2f}")
    print(
        f"Estimated year-end cost with {weeks_left_in_year} weeks left in year: ${ytd_unfiltered_cost + (weeks_left_in_year * filtered_total_cost) + (monthes_left_in_year * mtd_inverse_filtered_cost):,.2f}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--end-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
    )

    main(parser.parse_args().end_date)
