PG Logistics & Rent Tally Portal

1. Project Overview

This is a simple internal web application for managing the day-to-day logistics and rent tally of a PG business.

The current business has:

3 PG locations/buildings

Approximately 70 to 90 bed per building

Approximately 10 to 20 rooms per building

A mix of 2 BHK and 3 BHK or 1 room with Attached washroom configurations

Residents whose rent and deposit need to be tracked

Monthly rent collection that is currently maintained manually through sheets/marksheets

A month-end reconciliation process that is currently hectic and manual

The purpose of this application is not to become a full accounting system, payment gateway, or property-management platform.

It is primarily a tally and operational tracking system that replaces the current manual sheets.

The core principle is:

Enter the resident/room/payment information once, and let the application automatically show occupancy, rent collected, rent pending, vacant beds, upcoming move-outs, deposits held, and location-level revenue numbers.

2. Current Business Structure

The application must support multiple locations independently.

Current locations:

Location 1

Location 2

Location 3

The business may later expand to:

Location 4

Location 5

More locations in the future

The architecture therefore needs to be multi-location, but the application must remain simple.

Each location is treated as one PG/building.

All operational and financial information must be isolated by location.

For example:

Location A
    Residents
    Rooms
    Beds
    Rent
    Deposits
    Pending payments
    Move-outs

Location B
    Residents
    Rooms
    Beds
    Rent
    Deposits
    Pending payments
    Move-outs

Location C
    Residents
    Rooms
    Beds
    Rent
    Deposits
    Pending payments
    Move-outs

The owner/super admin can switch between locations and see the data for that location.

3. Authentication and Location Selection

The user first logs into the application.

After login, the user selects the PG/location they want to manage.

Basic flow:

Login
   ↓
Select Location
   ↓
Location Dashboard

The application should always make it obvious which location is currently selected.

Example:

Current Location: Kothrud PG

All data shown after selecting the location must belong only to that location.

4. User Roles

Only two roles are required.

4.1 Super Admin 

The Super Admin is the owner.

The Super Admin can:

Access all locations

Switch between locations

Add/edit/delete residents

Add/edit room and bed information

Assign residents to beds

Mark beds as vacant/occupied/available

Record rent payments

Mark residents as paid/unpaid

Track deposits

Record move-out/notice information

See all dashboards and analytics

See all financial summaries

Manage staff access

Correct operational mistakes

View historical records

The Super Admin has complete access.

4.2 Staff - specific to location

Staff access is intentionally limited.

Staff can see only the information necessary for daily operations.

Staff can:

See residents

See room/bed occupancy

See vacant beds

See occupied beds

See which residents have paid

See which residents have not paid

See pending rent

See move-out/notice information needed operationally

Staff should not have access to owner-level financial analytics or administrative controls.

Staff should not be able to manage system settings, users, or unrestricted financial records.

5. Building / Room Structure

The system should NOT use a complicated property-management model.

A simple room/bed representation is enough.

The business has buildings containing rooms, and every physical sleeping position can simply be represented by a human-readable bed identifier.

Example

Suppose a room has two non-attached beds.

Instead of exposing technical database IDs to the user, the application can show:

101-1NA
101-2NA

Where:

101 = Room 101

1 / 2 = Bed number

NA = Non-Attached

Similarly:

102-1A
102-2A

can represent two beds in an attached bedroom.

The exact naming convention can be adjusted, but the principle is:

The user should see a natural, human-readable bed identifier instead of technical IDs.

6. Example Building Layout

For a 2 BHK:

Hall
    3 people

Non-Attached Bedroom
    2 people

Attached Bedroom
    2 people

Total:

7 beds

For a 3 BHK:

Hall
    3 people

Bedroom 1
    2 people

Bedroom 2
    2 people

Bedroom 3
    2 people

Total:

9 beds

The application only needs to know:

Which room the bed belongs to

What the bed's human-readable identifier is

Whether the bed is available, vacant, or occupied

Which resident currently occupies it

There is no need for a complex room-allocation engine.

7. Bed Status

Only three statuses are required:

Available
Vacant
Occupied

These should be used consistently throughout the application.

Occupied

A resident currently lives in the bed.

To-be Vacant

The bed  will be available by X date

Available

The bed is available to be assigned/used.

The UI should make these statuses immediately understandable.

8. Resident Database

The resident database is the core operational database.

Each current resident should have a record containing the information actually needed by the business.

Resident information

Suggested fields:

Resident ID

Full Name

Phone Number

Location

Room

Bed

Monthly Rent

Security Deposit

Date Joined

Current Status

Move-Out Notice Date

Expected Move-Out Date

Notes

The system does not need a huge HR-style profile.

Do not overcomplicate resident records with unnecessary information.

9. Resident Status

Resident status should be simple.

Suggested statuses:

Active
Move-Out Notice
Left

Active

Currently living in the PG and not currently serving notice.

Move-Out Notice

The resident has formally given one month's notice and is expected to leave on a defined future date.

Left

The resident has moved out and no longer occupies the bed.

10. Historical Data Requirement

The system does NOT need a large historical tenancy engine.

Only approximately the last two months of useful historical information needs to be retained/visible for operational tracking.

Older data can be handled separately if necessary.

The goal is not to build an enterprise property-history system.

The focus is the current operating period and recent history.

11. Rent Model

Rent handling is intentionally simple.

Each resident has a monthly rent amount.

Examples:

Resident A
Monthly Rent = ₹8,000

Resident B
Monthly Rent = ₹9,000

The application uses this amount when calculating the month's expected incoming rent.

12. Payment Rules

The business follows a strict payment model.

No partial payments

Residents do NOT make partial rent payments.

A month's rent is either:

Paid

or:

Not Paid

The application therefore does not need:

Partial payment logic

Payment allocation logic

Split payments

Installment schedules

Complex receivables

This should remain deliberately simple.

13. Payment Tracking

The application is not a payment collection system.

No money will be collected through the application.

There will be no:

Payment gateway

UPI integration

Card payment

Online checkout

Bank integration

The application is only a manual tally tool.

The owner/staff records whether the resident has paid.

Example:

August 2026

Rahul     ₹8,000    PAID
Amit      ₹8,000    PAID
Sneha     ₹9,000    NOT PAID
Raj       ₹8,000    PAID

The system then calculates totals automatically.

14. Monthly Rent Ledger

The resident ledger is one of the most important features.

The ledger should show a simple month-by-month record of rent status.

Example:

Resident: Rahul

Month        Rent        Status
-----------------------------------
June         ₹8,000      Paid
July         ₹8,000      Paid
August       ₹8,000      Pending

This provides the historical record needed for quick checking.

The ledger does not need to become a full accounting ledger.

It is simply a clear record of:

What rent was due

Whether it was paid

When it was marked as paid

15. Payment Date

For every payment marked as received, the system should record:

Payment month

Amount

Date marked as paid

User who marked it

Example:

August Rent
Amount: ₹8,000
Status: Paid
Paid On: 05-Aug-2026
Marked By: Staff

This makes the ledger useful for month-end verification.

16. Expected Revenue vs Collected Revenue

The location dashboard must automatically calculate:

Expected Rent

Total rent expected from all currently applicable residents for the selected month.

Collected Rent

Total rent that has been marked as paid.

Pending Rent

Expected Rent minus Collected Rent.

Example:

Expected Rent     ₹5,60,000
Collected Rent    ₹5,12,000
Pending Rent         ₹48,000

17. Defaulter / Pending Rent View

One of the most important screens is the pending-payment list.

The application should show residents who have not paid.

Example:

Resident

Phone

Room

Bed

Rent

Status

Rahul

98XXXXXX12

101

101-1NA

₹8,000

Pending

Amit

97XXXXXX32

204

204-2A

₹9,000

Pending

The purpose is operational:

Immediately know who has not paid and contact them.

The list should be sortable/filterable.

Useful filters:

Paid

Not Paid

Room

Floor

Resident name

18. Occupancy Dashboard

The location dashboard must show the physical occupancy of the PG immediately.

Example:

Total Beds        70
Occupied          58
Vacant            12

The system should also show occupancy percentage.

Example:

Occupancy = 82.9%

This should be derived automatically from bed status.

19. Room-Level Occupancy

The user should be able to inspect the building room by room.

Example:

Room 101
101-1NA  Rahul      Occupied
101-2NA  Amit       Occupied

Room 102
102-1A   Sneha      Occupied
102-2A   VACANT     Vacant

Room 103
103-1A   Raj        Occupied
103-2A   VACANT     Vacant

This gives the owner a direct physical understanding of the PG.

The interface should primarily show natural names and readable identifiers rather than database terminology.

20. Vacancy / Empty Seat Tracking

The application should have a clear list of all vacant beds.

Example:

VACANT BEDS

101-2NA
103-1A
205-2A
207-1NA

This is useful for:

Sales

New admissions

Daily operations

Understanding lost capacity

21. Vacancy Revenue Loss

The dashboard should calculate the approximate revenue opportunity lost because beds are empty.

Example:

Vacant Beds                 6
Average Rent              ₹8,000

Potential Monthly Loss    ₹48,000

More accurately, the system can calculate this based on the actual rent associated with each vacant bed/resident slot where that information is known.

Example:

Vacant bed 101-2NA      ₹8,000 potential
Vacant bed 103-1A       ₹9,000 potential
Vacant bed 205-2A       ₹8,000 potential

Total potential loss   ₹25,000

This should appear as a dashboard metric.

22. Move-Out Notice Tracking

This is a required feature.

Notice period is fixed at:

1 month

When a resident gives notice, the application should record:

Notice given date

Expected move-out date

Resident

Room

Bed

Status = Move-Out Notice

Example:

Rahul
Room: 101
Bed: 101-1NA

Notice Given: 10-Aug-2026
Expected Move-Out: 10-Sep-2026
Status: Move-Out Notice

23. Upcoming Move-Out Dashboard

The system should show upcoming departures.

Example:

UPCOMING MOVE-OUTS

Resident     Bed        Notice Date     Move-Out Date
------------------------------------------------------
Rahul        101-1NA    10-Aug          10-Sep
Amit         203-2A     15-Aug          15-Sep
Sneha        204-1A     20-Aug          20-Sep

This is important because it allows the owner to anticipate vacancies before they actually happen.

24. Move-Out and Bed Release

When the resident actually leaves:

Resident is marked Left

Move-out date is recorded

Bed is changed to Vacant

Deposit settlement is recorded

The upcoming move-out entry is no longer shown as pending

This keeps occupancy accurate.

25. Deposit Model

The PG has a very simple deposit rule.

The resident pays a security deposit.

The deposit is recorded in the system.

The deposit is not treated as normal monthly revenue.

While leaving:



A mandatory ₹1,000 deduction applies to everyone.

Example:

Mandatory Deduction          ₹1,000
Refund                       ₹14,000

26. Deposit Tracking

For every resident, the system should know:

Deposit amount received

Whether the resident is active/left

Deposit refund status

Original deposit

Mandatory ₹1,000 deduction

Final refund amount

Example:


Deposit Received       ₹15,000
Mandatory Deduction     ₹1,000
Refund Due             ₹14,000

The system should make this easy to verify at move-out.

27. Deposit and Rent Relationship

Rent and deposit are tracked separately.

The application must never confuse:



with:



Rent contributes to expected/collected rental revenue.

Deposit is a security amount held against the resident and later refunded according to the PG's rule.

28. Financial Scope

The application is intentionally limited financially.

Included

Monthly rent expected

Monthly rent received

Monthly rent pending

Payment date

Resident rent ledger

Deposit received

Deposit refund calculation

Location-level revenue

Vacancy-related potential revenue loss

Month-end collection summary

Not Included

Expenses

Profit & loss accounting

Vendor management

Electricity accounting

Payroll

Tax accounting

Full Tally integration

Payment gateway

Bank reconciliation

Online payment collection

The application is primarily a revenue and occupancy tally system.

29. Location Dashboard

Each location should have one clear dashboard.

The user should be able to understand the entire PG at a glance.

Example:

==================================================
KOTHRUD PG
August 2026
==================================================

OCCUPANCY

Total Beds       70
Occupied         58
Vacant           12
Occupancy        82.9%

--------------------------------------------------

RENT

Expected         ₹5,60,000
Collected        ₹5,12,000
Pending             ₹48,000
Collection %       91.4%

--------------------------------------------------

PAYMENT STATUS

Paid Residents        58
Pending Residents      7
Move-Out Residents     5

--------------------------------------------------

VACANCY

Vacant Beds            12
Potential Revenue Loss ₹96,000

--------------------------------------------------

UPCOMING MOVE-OUTS

Next 30 Days             5

--------------------------------------------------

DEPOSITS

Deposits Held           ₹9,00,000
Pending Refunds         ₹28,000

==================================================

The exact figures above are examples only.

30. Location Isolation

Every record must belong to a location.

For example:

Resident → Location A
Room → Location A
Bed → Location A
Rent Record → Location A
Deposit → Location A
Move-Out → Location A

The application should never accidentally mix residents or financial figures across PGs.

When the user changes the selected location, all dashboard numbers and tables must update to that location only.

31. Main Application Sections

The application can remain very small.

Recommended main navigation:

Dashboard
Residents
Rooms & Beds
Rent
Move-Outs

Optional administrative section for Super Admin:

Locations
Users

That is enough for the current business.

32. Dashboard Detail

The dashboard should provide quick-action visibility.

Important cards

Total Beds
Occupied Beds
Vacant Beds
Occupancy %
Expected Rent
Collected Rent
Pending Rent
Collection %
Upcoming Move-Outs
Potential Vacancy Loss
Deposits Held

The most important operational lists should appear below the cards:

Pending Payments

People who have not paid.

Vacant Beds

All currently empty beds.

Upcoming Move-Outs

Residents who have given notice.

33. Residents Screen

The resident list should be searchable.

Example columns:

Name
Phone
Room
Bed
Rent
Deposit
Join Date
Status
Payment Status
Move-Out Date

Filters:

Active
Move-Out Notice
Left

Paid
Pending

Search should work by:

Name

Phone

Room

Bed

34. Resident Ledger Screen

When selecting a resident, the owner/staff should be able to see the simple ledger.

Example:

RAHUL SHARMA

Location: Kothrud
Room: 101
Bed: 101-1NA
Monthly Rent: ₹8,000
Deposit: ₹15,000

RENT LEDGER

June       ₹8,000     Paid
July       ₹8,000     Paid
August     ₹8,000     Pending

MOVE-OUT

Status: Active

The ledger is meant for quick verification, not formal accounting.

35. Rooms & Beds Screen

This should be a visual operational screen.

Example:

ROOM 101
-------------------------
101-1NA   Rahul    Occupied
101-2NA   Amit     Occupied

ROOM 102
-------------------------
102-1A    Sneha    Occupied
102-2A    VACANT   Vacant

ROOM 103
-------------------------
103-1A    Raj      Occupied
103-2A    VACANT   Vacant

The user should immediately understand where everyone is living.

36. Rent Screen

The rent screen should provide the monthly collection view.

Example:

AUGUST 2026

Expected Rent       ₹5,60,000
Collected Rent      ₹5,12,000
Pending Rent           ₹48,000
Collection Rate          91.4%

Below that:

Resident       Rent       Status       Paid Date
----------------------------------------------------
Rahul          ₹8,000     Paid         05-Aug
Amit           ₹8,000     Paid         03-Aug
Sneha          ₹9,000     Pending      -

This is the main monthly tally screen.

37. Move-Out Screen

The move-out screen should show residents currently under notice.

Example:

Resident     Bed        Notice Date     Move-Out
--------------------------------------------------
Rahul        101-1NA    10-Aug          10-Sep
Amit         203-2A     15-Aug          15-Sep

After the move-out happens, the resident can be marked as Left.

The bed becomes Vacant.

38. Month-End Reconciliation

One of the major reasons for building this application is to eliminate manual month-end work.

At month end, the owner should be able to see one summary:

MONTH-END SUMMARY
August 2026

Total Beds               70
Occupied                 58
Vacant                   12

Expected Rent       ₹5,60,000
Collected Rent      ₹5,12,000
Pending Rent           ₹48,000

Paid Residents            58
Pending Residents          7

New Move-Out Notices       5
Residents Left              3

Deposits Held         ₹9,00,000
Deposit Refunds         ₹28,000

Potential Vacancy Loss ₹96,000

This should replace the manual process of combining multiple sheets.

39. Data Model

The application should use a simple relational database structure.

Recommended core entities:

users
locations
rooms
beds
residents
resident_stays
rent_records
payments
deposits
move_out_notices

users

Stores application users and roles.

locations

Stores each PG/building.

rooms

Stores rooms inside each location.

beds

Stores individual beds/seats.

residents

Stores resident information.

resident_stays

Stores the resident's current/recent room/bed relationship and dates.

rent_records

Stores monthly rent due and payment status.

payments

Stores when rent was marked as received.

deposits

Stores deposit amounts and refund information.

move_out_notices

Stores one-month notice information.

40. Recommended Database Relationship

Conceptually:

USER
 |
 +---- role

LOCATION
 |
 +---- ROOM
        |
        +---- BED
               |
               +---- RESIDENT
                       |
                       +---- RENT RECORDS
                       |
                       +---- PAYMENTS
                       |
                       +---- DEPOSIT
                       |
                       +---- MOVE-OUT NOTICE

Every operational record must also be traceable back to the location.

41. Suggested Technical Architecture

The application will use a simple modern web stack.

Frontend

Next.js

Hosted on:

Vercel

Backend

FastAPI

Hosted on:

Render

Database / Backend Services

Supabase

Using:

PostgreSQL
Supabase Authentication
Supabase Storage (only if needed later)

The application is intentionally designed to work on free hosting initially.

42. Backend Responsibility

The backend should handle business logic such as:

Resident creation/update

Room/bed assignment

Payment marking

Rent calculations

Deposit calculations

Move-out calculations

Occupancy calculations

Location-level statistics

Permission checks

Month-end summaries

The backend should ensure that business rules cannot be accidentally bypassed from the frontend.

43. Frontend Responsibility

The frontend should focus on:

Login

Location selection

Dashboard

Tables

Filters

Forms

Occupancy visualization

Rent status visualization

Move-out tracking

The interface should be simple enough that someone who currently manages the PG using spreadsheets can use it immediately.

44. Design Philosophy

The application should prioritize:

Simplicity

Speed of data entry

Easy month-end verification

Clear occupancy visibility

Clear rent collection visibility

Minimal manual calculation

Human-readable room/bed naming

Location isolation

Reliable data

Very low operational complexity

It should NOT attempt to become:

A full ERP

A full accounting system

A property marketplace

A payment platform

A CRM

A complicated property-management suite

45. What the System Should Automate

The user should manually provide only the important operational facts.

For example:

Resident joined
Resident assigned to bed
Resident's rent amount
Resident's deposit
Rent marked as paid
Resident gave notice
Resident moved out
Deposit refunded

The application should automatically calculate:

Occupied beds
Vacant beds
Occupancy %
Expected monthly rent
Collected monthly rent
Pending rent
Collection %
Pending residents
Potential revenue lost from vacancies
Upcoming move-outs
Deposit refund amount
Month-end summary

This is the main value of the application.

46. What the System Should NOT Automate

The following are deliberately outside the current scope:

Payment collection
Payment gateway
UPI integration
Expense tracking
Profit & loss
Accounting
Tax
Payroll
Vendor management
Electricity billing
Complex historical tenancy management
Complex room allocation
Partial payments
Online resident portal
Resident login

These can be considered later only if the business actually needs them.

47. MVP Definition

The MVP is complete when the owner can:

Log in

Select a PG/location

See the location dashboard

See all residents

See where each resident is staying

See every room and bed

See occupied/vacant beds

Mark monthly rent as paid

See who has not paid

See the pending amount

See the payment date

See each resident's simple rent ledger

Track deposits

Record one-month move-out notices

See upcoming move-outs

Mark residents as left

Release their beds

See monthly expected revenue

See monthly collected revenue

See monthly pending revenue

See vacancy-related potential revenue loss

View a clean month-end summary

48. Final Product Definition

The product is a:

Simple multi-location PG Logistics and Rent Tally Portal.

It replaces the current manual spreadsheet-based tracking process with one centralized application.

The system revolves around five core questions:

1. Who is living here?

Resident + room + bed.

2. Where are they living?

Room + human-readable bed identifier.

3. Who has paid?

Monthly rent status + payment date.

4. Who has not paid?

Pending rent list + resident phone number.

5. What is the current state of this PG?

Occupancy + vacant beds + expected revenue + collected revenue + pending revenue + move-outs + deposits.

The application should make these answers available immediately without requiring month-end manual reconciliation.

49. Example End-to-End Workflow

New Resident

Add Resident
    ↓
Select Location
    ↓
Select Room
    ↓
Select Bed
    ↓
Enter Monthly Rent
    ↓
Enter Deposit
    ↓
Resident becomes ACTIVE
    ↓
Bed becomes OCCUPIED

Monthly Rent

Month begins
    ↓
System generates/recognizes rent due
    ↓
Staff checks payment externally
    ↓
Staff marks PAID
    ↓
Payment date recorded
    ↓
Dashboard updates automatically

Resident Has Not Paid

Rent remains PENDING
    ↓
Resident appears in Defaulters/Pending list
    ↓
Phone number is visible
    ↓
Pending revenue increases

Resident Gives Notice

Mark Move-Out Notice
    ↓
Notice date recorded
    ↓
Expected move-out = +1 month
    ↓
Resident appears in Upcoming Move-Outs

Resident Leaves

Mark Resident as LEFT
    ↓
Bed becomes VACANT
    ↓
Deposit refund calculated
    ↓
₹1,000 mandatory deduction applied
    ↓
Refund amount recorded
    ↓
Occupancy and vacancy numbers update

50. Core Principle

The final system should feel like a digital replacement for the existing PG notebook/spreadsheet system, not like a giant enterprise application.

The owner should be able to open one location and immediately answer:

How many beds do I have?
How many are occupied?
How many are vacant?
Who is living where?
Who has paid?
Who has not paid?
How much rent should I have received?
How much have I received?
How much is pending?
Who is leaving next month?
How much deposit is being held?
What is my vacancy revenue loss?
What does my month-end tally look like?

That is the complete purpose of the MVP.