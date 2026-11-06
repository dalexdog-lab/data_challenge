# BANK RESEARCH: THE ILLUSION OF BANKING CHOICE
#
# Put these files in your working folder:
#   bank_quarter.csv
#   branches.csv
#   events.csv
#
# If needed, install the required packages in your terminal:
# python -m pip install numpy pandas matplotlib
#
# In Jupyter, use this command in a separate cell instead:
# %pip install numpy pandas matplotlib
#
# The installation commands above are comments.
# They do not run automatically.
#
# New tables and charts will be saved in bank_research_outputs.


# 1. LOAD THE TOOLS

# Tools that come with Python.
from pathlib import Path   # Build file and folder paths.
import json                # Save the analysis settings.
import sys                 # Show which Python version is running.

# Tools installed separately.
import numpy as np         # Numerical calculations.
import pandas as pd        # Tables.
import matplotlib          # Charting package.
import matplotlib.pyplot as plt  # Draw and label charts.

# Make printed tables easier to read.
pd.set_option("display.max_columns", 12)
pd.set_option("display.width", 140)

# Show the versions used for this run.
print("Python:", sys.version.split()[0])
print("pandas:", pd.__version__)
print("numpy:", np.__version__)
print("matplotlib:", matplotlib.__version__)


# 2. CHOOSE THE FILE LOCATIONS, DATES, AND SAMPLE RULES

# A period means "the current working folder".
# Change this if your CSV files are somewhere else.
# Windows example:
# DATA_DIR = Path(r"C:\Users\Alex\Downloads\BankResearch")
DATA_DIR = Path(".")

# Store new tables and charts in their own folder.
OUTPUT_DIR = Path("bank_research_outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

# Measure bank characteristics before the failures being studied.
BASELINE_YEAR = 2006
BASELINE_DATE = "2006-06-30"

# Count only failures occurring inside this later period.
FAILURE_START = pd.Timestamp("2007-01-01")
FAILURE_END = pd.Timestamp("2012-12-31")

# Require usable financial information for at least:
#   90% of a county's selected deposits, AND
#   90% of its selected banks.
MIN_COVERAGE = 0.90

# Code 11 selects full-service brick-and-mortar offices.
SERVICE_TYPES = [11]


# 2A. LIST THE COLUMNS WE WILL USE

# Eight kinds of lending used to compare the banks.
LOAN_COLS = [
    "loans_residential_mortgage",    # Home mortgage lending.
    "loans_construction",           # Construction and development lending.
    "loans_commercial_real_estate", # Commercial property lending.
    "loans_multifamily",            # Multifamily housing lending.
    "loans_farmland",               # Loans secured by farmland.
    "loans_agricultural",           # Agricultural lending.
    "loans_commercial_industrial",  # Business lending.
    "loans_consumer_total",         # Total consumer lending.
]

# Financial information for each bank.
# "+ LOAN_COLS" adds the list above.
FINANCIAL_COLS = [
    "cert",
    "report_date",
    "total_assets",
    "loans_gross",
    "equity_to_assets_pct",
    "noncurrent_rate_pct",
] + LOAN_COLS

# Location and deposit information for each office.
BRANCH_COLS = [
    "year",
    "cert",
    "county_fips",
    "county_name",
    "state",
    "service_type",
    "branch_deposits",
    "source_record_id",
]

# Stop early if an input file cannot be found.
for filename in ["bank_quarter.csv", "branches.csv", "events.csv"]:
    file_path = DATA_DIR / filename

    if not file_path.is_file():
        raise FileNotFoundError(
            f"Put {filename} in DATA_DIR, or change DATA_DIR above."
        )


# 3. CREATE A HELPER FOR READING LARGE CSV FILES

def read_filtered_csv(path, columns, keep_rows, dtype=None):
    """Read a large CSV in pieces and return only the rows we want.

    path: the CSV file to read.
    columns: the list of columns needed.
    keep_rows: a function deciding which rows to keep.
    dtype: optional instructions for treating columns as text, etc.
    """

    # Collect the relevant rows from each batch.
    pieces = []

    # Read 100,000 rows at a time.
    batches = pd.read_csv(
        path,
        usecols=columns,
        dtype=dtype,
        chunksize=100_000,
    )

    for batch in batches:
        # The filter gives True for wanted rows and False for other rows.
        wanted_rows = keep_rows(batch)

        # Keep those rows in a separate table.
        selected_rows = batch.loc[wanted_rows].copy()

        if not selected_rows.empty:
            pieces.append(selected_rows)

    if not pieces:
        raise ValueError(f"No matching rows in {path.name}.")

    # Join the saved batches into one table.
    return pd.concat(pieces, ignore_index=True)


# 3A. READ THE THREE FILES

def is_baseline_financial_row(batch):
    """Keep financial reports from June 30, 2006."""
    return batch["report_date"] == BASELINE_DATE


def is_baseline_branch_row(batch):
    """Keep office records from 2006."""
    return batch["year"] == BASELINE_YEAR


banks = read_filtered_csv(
    path=DATA_DIR / "bank_quarter.csv",
    columns=FINANCIAL_COLS,
    keep_rows=is_baseline_financial_row,
)

branches = read_filtered_csv(
    path=DATA_DIR / "branches.csv",
    columns=BRANCH_COLS,
    keep_rows=is_baseline_branch_row,

    # County IDs are text so their leading zeroes are preserved.
    dtype={"county_fips": "string"},
)

# The events file is small enough to read in one operation.
events = pd.read_csv(
    DATA_DIR / "events.csv",
    usecols=["cert", "event_date", "event_type"],
)

# Convert date text into dates Python can compare.
events["event_date"] = pd.to_datetime(
    events["event_date"],
    errors="raise",
)


# 3B. CHECK THE STARTING RECORDS

# An assert stops the program if a required condition is false.

# Each bank should have one financial report at the chosen date.
assert banks["cert"].is_unique, "Duplicate baseline bank reports."

# Each selected office record should appear once.
assert branches["source_record_id"].is_unique, "Duplicate office records."

# Bank IDs must be present to connect the files.
assert banks["cert"].notna().all(), "A financial record has no bank ID."
assert branches["cert"].notna().all(), "An office record has no bank ID."

print(f"Baseline financial records: {len(banks):,}")
print(f"Baseline office records before filters: {len(branches):,}")


# 4. CHECK MISSING FINANCIAL INFORMATION

# These fields are needed for the lending score and comparison controls.
required = LOAN_COLS + [
    "total_assets",
    "loans_gross",
    "equity_to_assets_pct",
    "noncurrent_rate_pct",
]

# isna() finds blanks.
# sum() counts them for each column.
missing_counts = banks[required].isna().sum()

print("\nMissing values at the baseline date:")
print(missing_counts.to_string())

# Give each condition a descriptive name.
has_all_required_values = banks[required].notna().all(axis=1)

has_no_negative_loan_balances = (
    banks[LOAN_COLS].ge(0).all(axis=1)
)

has_some_reported_lending = (
    banks[LOAN_COLS].sum(axis=1).gt(0)
)

has_positive_assets = banks["total_assets"].gt(0)

has_positive_total_loans = banks["loans_gross"].gt(0)

# & means AND: a bank must meet every condition.
banks["portfolio_ok"] = (
    has_all_required_values
    & has_no_negative_loan_balances
    & has_some_reported_lending
    & has_positive_assets
    & has_positive_total_loans
)

usable_count = banks["portfolio_ok"].sum()

print(f"\nBanks with usable loan profiles and controls: {usable_count:,}")
print(f"Banks without all required information: {len(banks) - usable_count:,}")


# 5. COMBINE OFFICES BELONGING TO THE SAME BANK IN THE SAME COUNTY

# First, check that office deposits are present and nonnegative.
assert branches["branch_deposits"].notna().all(), "Missing office deposits."
assert branches["branch_deposits"].ge(0).all(), "Negative office deposits."

# Keep the selected office types and offices with positive deposits.
is_selected_service = branches["service_type"].isin(SERVICE_TYPES)
has_positive_deposits = branches["branch_deposits"] > 0

offices = branches.loc[
    is_selected_service & has_positive_deposits
].copy()

# Every selected office needs location information.
location_fields = ["county_fips", "county_name", "state"]

assert offices[location_fields].notna().all().all()

# Each county identifier should contain five digits.
assert offices["county_fips"].str.fullmatch(r"\d{5}").all()

# Combine all offices belonging to one bank in one county.
# One row now means ONE BANK IN ONE COUNTY.
local_banks = offices.groupby(
    ["county_fips", "county_name", "state", "cert"],
    as_index=False,
).agg(
    local_deposits=("branch_deposits", "sum"),
    office_count=("cert", "size"),
)

# Add bank-wide financial information using the shared bank ID.
# "many_to_one" checks that each bank has one financial record.
local_banks = local_banks.merge(
    banks,
    on="cert",
    how="left",
    validate="many_to_one",
)

# An unmatched bank has no usable financial profile.
# Its deposits still remain in the starting county totals.
local_banks["portfolio_ok"] = local_banks["portfolio_ok"].eq(True)

# Check that the join did not create or lose deposits.
assert np.isclose(
    local_banks["local_deposits"].sum(),
    offices["branch_deposits"].sum(),
)

print(f"\nBank-county combinations: {len(local_banks):,}")


# 5A. MARK LATER FAILURES AND MERGERS

# Select event dates inside the follow-up window, including both ends.
in_window = events["event_date"].between(
    FAILURE_START,
    FAILURE_END,
)

is_failure = events["event_type"] == "failure"
is_merger = events["event_type"] == "merger"

# Sets hold unique bank IDs.
failed_certs = set(
    events.loc[in_window & is_failure, "cert"]
)

merged_certs = set(
    events.loc[in_window & is_merger, "cert"]
)

# isin() checks whether each bank ID belongs to the relevant set.
local_banks["failed_in_window"] = (
    local_banks["cert"].isin(failed_certs)
)

local_banks["merged_in_window"] = (
    local_banks["cert"].isin(merged_certs)
)

failed_baseline_banks = local_banks.loc[
    local_banks["failed_in_window"],
    "cert",
].nunique()

print(f"Failure events in the follow-up window: {len(failed_certs):,}")
print(f"Baseline institutions that later failed: {failed_baseline_banks:,}")


# 6. CREATE THE LENDING-SIMILARITY CALCULATION

def lending_similarity(
    loan_balances,
    local_deposits,
    equal_weight=False,
):
    """Return one county's lending-similarity score, from 0 to 1.

    Each row of loan_balances describes one bank's loan balances.
    local_deposits gives those banks' deposits in this county.

    A score of 1 means identical lending proportions.
    A score of 0 means no overlap in the loan categories.

    equal_weight=True treats each bank equally for a later check.
    """

    loan_matrix = np.asarray(loan_balances, dtype=float)
    weights = np.asarray(local_deposits, dtype=float)

    # Comparing banks requires at least two usable banks.
    if len(loan_matrix) < 2:
        return np.nan

    if equal_weight:
        weights = np.ones(len(loan_matrix))

    # Convert deposits into weights that add to 1.
    weights = weights / weights.sum()

    # Scale each bank's row to length 1.
    # This removes size differences while preserving loan proportions.
    row_lengths = np.linalg.norm(
        loan_matrix,
        axis=1,
        keepdims=True,
    )

    unit_profiles = loan_matrix / row_lengths

    # @ means matrix multiplication.
    # .T switches rows and columns.
    # The result compares every bank with every other bank.
    pair_similarities = unit_profiles @ unit_profiles.T

    # Weight bank pairs using their local deposit shares.
    pair_weights = np.outer(weights, weights)

    # Remove comparisons of a bank with itself.
    np.fill_diagonal(pair_weights, 0.0)

    weighted_total = (
        pair_similarities * pair_weights
    ).sum()

    total_pair_weight = pair_weights.sum()

    return float(weighted_total / total_pair_weight)


# 6A. CHECK THE CALCULATION USING SIMPLE EXAMPLES

same_proportions = lending_similarity(
    loan_balances=[[80, 20], [800, 200]],
    local_deposits=[1, 1],
)

different_categories = lending_similarity(
    loan_balances=[[100, 0], [0, 100]],
    local_deposits=[1, 1],
)

# These examples should produce 1 and 0.
assert np.isclose(same_proportions, 1.0)
assert np.isclose(different_categories, 0.0)

print("\nSame lending proportions:", same_proportions)
print("Completely different categories:", different_categories)


# 7. CREATE THE COUNTY-LEVEL ANALYSIS TABLE

# 7A. CALCULATE STARTING MARKET SHARES AND FAILURE EXPOSURE

def starting_county_statistics(
    fips,
    name,
    state,
    county_banks,
):
    """Summarize all selected banks in one county."""

    total_deposits = county_banks["local_deposits"].sum()

    deposit_shares = (
        county_banks["local_deposits"].to_numpy(float)
        / total_deposits
    )

    # Select usable profiles to calculate how much data we have.
    usable_banks = county_banks.loc[
        county_banks["portfolio_ok"]
    ]

    usable_deposits = usable_banks["local_deposits"].sum()

    # True behaves like 1, and False like 0, in calculations.
    failure_flags = (
        county_banks["failed_in_window"].to_numpy()
    )

    merger_flags = (
        county_banks["merged_in_window"].to_numpy()
    )

    # Add the starting deposit shares of banks that later failed.
    # Multiply by 100 to express the answer as a percentage.
    failure_exposure = 100 * np.sum(
        deposit_shares * failure_flags
    )

    merger_exposure = 100 * np.sum(
        deposit_shares * merger_flags
    )

    # HHI measures deposit concentration.
    # Higher values mean fewer banks hold most of the deposits.
    concentration = float(
        np.sum(deposit_shares ** 2)
    )

    return {
        "county_fips": fips,
        "county_name": name,
        "state": state,
        "bank_count": len(county_banks),
        "usable_bank_count": len(usable_banks),
        "deposit_coverage": usable_deposits / total_deposits,
        "bank_coverage": len(usable_banks) / len(county_banks),
        "deposit_hhi": concentration,
        "failure_exposure_pct": float(failure_exposure),
        "failed_bank_count": int(
            county_banks["failed_in_window"].sum()
        ),
        "merger_exposure_pct": float(merger_exposure),
    }


# 7B. CALCULATE SIMILARITY AND OTHER STARTING CHARACTERISTICS

# Names for the county-average loan shares.
MIX_COLS = [
    "mix_" + column.removeprefix("loans_")
    for column in LOAN_COLS
]


def usable_bank_statistics(usable_banks):
    """Calculate similarity and controls for the usable banks."""

    usable_deposits = usable_banks["local_deposits"].sum()

    # These weights add to 1 among the usable banks.
    weights = (
        usable_banks["local_deposits"].to_numpy(float)
        / usable_deposits
    )

    loan_balances = (
        usable_banks[LOAN_COLS].to_numpy(float)
    )

    # Calculate shares within the eight reported loan categories.
    total_reported_balances = loan_balances.sum(
        axis=1,
        keepdims=True,
    )

    loan_shares = (
        loan_balances / total_reported_balances
    )

    assets = usable_banks["total_assets"].to_numpy(float)

    equity_ratios = (
        usable_banks["equity_to_assets_pct"].to_numpy(float)
    )

    problem_loan_rates = (
        usable_banks["noncurrent_rate_pct"].to_numpy(float)
    )

    statistics = {
        "similarity": lending_similarity(
            loan_balances,
            usable_banks["local_deposits"],
        ),

        "similarity_equal_weight": lending_similarity(
            loan_balances,
            usable_banks["local_deposits"],
            equal_weight=True,
        ),

        # weights @ values calculates a weighted average.
        # Logging assets reduces the influence of extreme bank sizes.
        "avg_log_assets": float(
            weights @ np.log(assets)
        ),

        "avg_equity_pct": float(
            weights @ equity_ratios
        ),

        "avg_noncurrent_pct": float(
            weights @ problem_loan_rates
        ),
    }

    # Add the county-average share for each loan category.
    average_loan_shares = weights @ loan_shares

    for column_name, average_share in zip(
        MIX_COLS,
        average_loan_shares,
    ):
        statistics[column_name] = average_share

    return statistics


# 7C. REPEAT THE CALCULATIONS FOR EVERY COUNTY

county_rows = []

county_groups = local_banks.groupby(
    ["county_fips", "county_name", "state"]
)

for (fips, name, state), county_banks in county_groups:
    # Include all selected starting deposits in the exposure calculation.
    row = starting_county_statistics(
        fips,
        name,
        state,
        county_banks,
    )

    usable_banks = county_banks.loc[
        county_banks["portfolio_ok"]
    ].copy()

    # Calculate similarity only with two or more usable banks.
    if len(usable_banks) >= 2:
        row.update(
            usable_bank_statistics(usable_banks)
        )

    county_rows.append(row)

# Convert the collected results into a table.
county_all = pd.DataFrame(county_rows)

print(
    f"\nCounties represented before coverage rules: "
    f"{len(county_all):,}"
)


# 7D. KEEP COUNTIES WITH ENOUGH INFORMATION

def select_counties(table, minimum_coverage):
    """Keep counties meeting the bank and coverage rules."""

    has_multiple_banks = (
        table["bank_count"] >= 2
    )

    has_multiple_usable_banks = (
        table["usable_bank_count"] >= 2
    )

    # The tiny tolerance handles computer rounding differences.
    has_enough_deposit_data = (
        table["deposit_coverage"]
        >= minimum_coverage - 1e-10
    )

    has_enough_bank_data = (
        table["bank_coverage"]
        >= minimum_coverage - 1e-10
    )

    has_similarity_score = (
        table["similarity"].notna()
    )

    keep = (
        has_multiple_banks
        & has_multiple_usable_banks
        & has_enough_deposit_data
        & has_enough_bank_data
        & has_similarity_score
    )

    return table.loc[keep].copy()


county = select_counties(
    county_all,
    MIN_COVERAGE,
)

# Check the final county table.
assert not county.empty, "No counties meet the coverage rules."

assert county["county_fips"].is_unique

assert county["similarity"].between(
    -1e-10,
    1 + 1e-10,
).all()

assert county["failure_exposure_pct"].between(
    0,
    100 + 1e-8,
).all()

numeric_fields = MIX_COLS + [
    "similarity",
    "avg_log_assets",
    "avg_equity_pct",
    "avg_noncurrent_pct",
]

assert np.isfinite(
    county[numeric_fields]
).all().all()

print(f"Counties retained: {len(county):,}")

print(
    "Retained counties with later failure exposure:",
    county["failed_bank_count"].gt(0).sum(),
)


# 7E. PRINT BASIC SUMMARY STATISTICS

summary_fields = [
    "similarity",
    "bank_count",
    "failure_exposure_pct",
    "deposit_coverage",
    "merger_exposure_pct",
]

print(
    county[summary_fields]
    .describe()
    .round(3)
    .to_string()
)


# 8. COMPARE LOWER-, MIDDLE-, AND HIGHER-SIMILARITY COUNTIES

GROUP_LABELS = [
    "Lower similarity",
    "Middle similarity",
    "Higher similarity",
]

# Divide counties into three approximately equal-sized groups.
county["similarity_group"] = pd.qcut(
    county["similarity"],
    q=3,
    labels=GROUP_LABELS,
)

# Each county receives equal weight in these averages.
group_comparison = county.groupby(
    "similarity_group",
    observed=True,
).agg(
    counties=("county_fips", "size"),
    mean_similarity=("similarity", "mean"),
    average_bank_count=("bank_count", "mean"),
    mean_failure_exposure_pct=("failure_exposure_pct", "mean"),
)

print("\nUnadjusted comparison:")
print(group_comparison.round(3).to_string())


# 8A. DRAW THE FIRST CHART

fig, ax = plt.subplots(figsize=(8, 4.6))

ax.bar(
    GROUP_LABELS,
    group_comparison["mean_failure_exposure_pct"],
    color=["#4f7f97", "#769caf", "#ac543d"],
)

ax.set_ylabel("Average failure exposure (%)")

ax.set_title(
    "County failure exposure by pre-crisis lending similarity"
)

ax.spines[["top", "right"]].set_visible(False)

caption = (
    "Exposure: June 2006 deposits at banks that failed in 2007–2012.\n"
    "Unadjusted county averages."
)

fig.text(
    0.12,
    0.01,
    caption,
    fontsize=9,
)

fig.tight_layout(rect=[0, 0.08, 1, 1])

fig.savefig(
    OUTPUT_DIR / "unadjusted_comparison.png",
    dpi=170,
)

# Both charts are displayed at the end of the script.


# 9. MAKE AN ADJUSTED COMPARISON

# This section accounts for other measured differences between counties.
# The coefficient describes an association, not proof of causation.

# 9A. BUILD THE TABLE OF COMPARISON FACTORS

def make_control_matrix(data, controls):
    """Build numerical columns for the other measured differences."""

    # The intercept provides an overall starting level.
    pieces = [
        pd.DataFrame({
            "intercept": np.ones(len(data))
        })
    ]

    if controls != "none":
        # Treat each exact bank count as a category, alongside states.
        categories = (
            data[["bank_count", "state"]]
            .astype(str)
            .reset_index(drop=True)
        )

        # Convert categories into columns of zeroes and ones.
        indicators = pd.get_dummies(
            categories,
            drop_first=True,
            dtype=float,
        )

        pieces.append(indicators)

    if controls == "full":
        # Omit one loan share because the eight shares add to 1.
        control_names = [
            "deposit_hhi",
            "avg_log_assets",
            "avg_equity_pct",
            "avg_noncurrent_pct",
        ] + MIX_COLS[:-1]

        numerical_controls = (
            data[control_names]
            .reset_index(drop=True)
        )

        column_means = numerical_controls.mean()

        column_scales = (
            numerical_controls.std(ddof=0)
            .replace(0, 1)
        )

        # Put numerical controls on comparable scales.
        standardized = (
            numerical_controls - column_means
        ) / column_scales

        pieces.append(standardized)

    # Join the pieces side by side.
    return pd.concat(
        pieces,
        axis=1,
    ).to_numpy(float)


# 9B. CALCULATE THE ADJUSTED ASSOCIATION

def adjusted_association(
    data,
    score_column="similarity",
    controls="full",
):
    """Return the slope and the values remaining after controls."""

    # A one-unit change here means a 0.10 change in similarity.
    similarity_units = (
        data[score_column].to_numpy(float) / 0.10
    )

    failure_exposure = (
        data["failure_exposure_pct"].to_numpy(float)
    )

    control_matrix = make_control_matrix(
        data,
        controls,
    )

    # Fit similarity using the other county characteristics.
    score_fit, _residuals, _rank, _singular_values = (
        np.linalg.lstsq(
            control_matrix,
            similarity_units,
            rcond=None,
        )
    )

    explained_similarity = (
        control_matrix @ score_fit
    )

    residual_similarity = (
        similarity_units - explained_similarity
    )

    # Fit failure exposure using those same characteristics.
    exposure_fit, _residuals, _rank, _singular_values = (
        np.linalg.lstsq(
            control_matrix,
            failure_exposure,
            rcond=None,
        )
    )

    explained_exposure = (
        control_matrix @ exposure_fit
    )

    residual_exposure = (
        failure_exposure - explained_exposure
    )

    # Find the slope relating the two sets of remaining values.
    numerator = (
        residual_similarity @ residual_exposure
    )

    denominator = (
        residual_similarity @ residual_similarity
    )

    if denominator <= 1e-12:
        raise ValueError(
            "No similarity variation remains after controls."
        )

    coefficient = float(numerator / denominator)

    return (
        coefficient,
        residual_similarity,
        residual_exposure,
    )


# 9C. RUN THREE VERSIONS OF THE COMPARISON

model_choices = [
    ("Similarity only", "none"),
    ("Exact bank count and state", "counts"),
    ("Full baseline controls", "full"),
]

model_rows = []

for model_name, control_set in model_choices:
    # We only need the coefficient inside this loop.
    coefficient, _, _ = adjusted_association(
        county,
        controls=control_set,
    )

    model_rows.append({
        "comparison": model_name,
        "counties": len(county),
        "exposure_pp_per_0_10_similarity": coefficient,
    })

model_comparison = pd.DataFrame(model_rows)

print("\nAdjusted comparisons:")
print(
    model_comparison.round(4).to_string(index=False)
)

# Save the full model's slope and residuals for the next chart.
main_coefficient, residual_x, residual_y = (
    adjusted_association(county)
)

print(
    f"\nFull-model descriptive association: "
    f"{main_coefficient:+.3f} percentage points "
    "per 0.10 similarity."
)

print(
    "These coefficients do not establish causation "
    "or statistical significance."
)


# 9D. DRAW THE ADJUSTED RELATIONSHIP

fig, ax = plt.subplots(figsize=(8, 4.8))

# Each dot represents one county after accounting for the controls.
ax.scatter(
    residual_x,
    residual_y,
    s=10,
    alpha=0.25,
    color="#4f7f97",
)

# Two endpoints are enough to draw a straight line.
line_x = np.array([
    residual_x.min(),
    residual_x.max(),
])

line_y = main_coefficient * line_x

ax.plot(
    line_x,
    line_y,
    color="#ac543d",
    linewidth=2,
)

ax.axhline(
    0,
    color="#b5b5b5",
    linewidth=0.6,
)

ax.set_xlabel(
    "Similarity remaining after controls (units of 0.10)"
)

ax.set_ylabel(
    "Failure exposure remaining after controls (percentage points)"
)

ax.set_title(
    "Adjusted association between similarity and failure exposure"
)

ax.spines[["top", "right"]].set_visible(False)

fig.tight_layout()

fig.savefig(
    OUTPUT_DIR / "adjusted_association.png",
    dpi=170,
)


# 10. CHECK WHETHER REASONABLE CHOICES CHANGE THE ANSWER

sensitivity_rows = []

# Repeat the analysis with three completeness requirements.
for threshold in [0.80, 0.90, 1.00]:
    sample = select_counties(
        county_all,
        threshold,
    )

    coefficient, _, _ = adjusted_association(sample)

    sensitivity_rows.append({
        "check": (
            f"Deposit-weighted similarity; "
            f"{threshold:.0%} coverage"
        ),
        "counties": len(sample),
        "exposure_pp_per_0_10_similarity": coefficient,
    })

# Keep the main sample, but weight banks equally in the similarity score.
coefficient, _, _ = adjusted_association(
    county,
    score_column="similarity_equal_weight",
)

sensitivity_rows.append({
    "check": "Equal-bank-weight similarity; 90% coverage",
    "counties": len(county),
    "exposure_pp_per_0_10_similarity": coefficient,
})

sensitivity = pd.DataFrame(sensitivity_rows)

print("\nSensitivity checks:")
print(
    sensitivity.round(4).to_string(index=False)
)


# 11. SAVE THE TABLES

# All counties, including those excluded by the coverage rules.
county_all.to_csv(
    OUTPUT_DIR / "county_audit_all.csv",
    index=False,
)

# Counties included in the main comparison.
county.to_csv(
    OUTPUT_DIR / "county_analysis.csv",
    index=False,
)

# The unadjusted comparison.
group_comparison.to_csv(
    OUTPUT_DIR / "unadjusted_comparison.csv"
)

# The adjusted comparisons.
model_comparison.to_csv(
    OUTPUT_DIR / "adjusted_comparisons.csv",
    index=False,
)

# The checks using alternative choices.
sensitivity.to_csv(
    OUTPUT_DIR / "sensitivity_checks.csv",
    index=False,
)


# 11A. SAVE THE ANALYSIS SETTINGS

audit = {
    "baseline_date": BASELINE_DATE,

    "failure_window": [
        str(FAILURE_START.date()),
        str(FAILURE_END.date()),
    ],

    "service_type_codes": SERVICE_TYPES,
    "positive_branch_deposits_only": True,
    "minimum_deposit_and_bank_coverage": MIN_COVERAGE,

    "baseline_bank_rows": len(banks),

    "usable_baseline_banks": int(
        banks["portfolio_ok"].sum()
    ),

    "bank_county_rows": len(local_banks),

    "counties_before_coverage_rules": len(county_all),

    "counties_in_primary_analysis": len(county),

    "counties_with_direct_failure_exposure": int(
        county["failed_bank_count"].gt(0).sum()
    ),

    "full_model_descriptive_coefficient": main_coefficient,

    "outcome": (
        "Percentage of selected baseline office deposits "
        "at institutions that directly failed "
        "in the follow-up window"
    ),

    "merger_handling": (
        "Kept in the baseline cohort and flagged separately; "
        "successor failures are not traced"
    ),

    "software_versions": {
        "python": sys.version.split()[0],
        "pandas": pd.__version__,
        "numpy": np.__version__,
        "matplotlib": matplotlib.__version__,
    },
}

audit_path = OUTPUT_DIR / "analysis_choices.json"

audit_path.write_text(
    json.dumps(audit, indent=2),
    encoding="utf-8",
)

print(
    "\nSaved analysis tables and charts in:",
    OUTPUT_DIR.resolve(),
)


# 12. DISPLAY THE CHARTS

# Read the results alongside the coverage and sensitivity checks.
# These are exploratory associations.
# They do not establish causation or statistical significance.
# Failure exposure does not measure money lost by depositors.

plt.show()