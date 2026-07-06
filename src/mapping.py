# The skill -> LOB mapping is managed entirely from the Mapping Manager tab
# (upload / edit / Apply). There is intentionally NO built-in mapping baked
# into the code: after a redeploy (which wipes the server disk), re-import
# the saved mapping Excel in the Mapping Manager.
SKILL_TO_LOB = {}

# Targets per LOB — May 2026 (most recent period in Target sheet)
# Keys: aht (seconds), asa (seconds), abn (ratio 0–1)
TARGETS = {
    'Sales': {'aht': 362, 'asa': 13, 'abn': 0.03},
    'CCM': {'aht': 312, 'asa': 120, 'abn': 0.03},
    'International': {'aht': 415, 'asa': 47, 'abn': 0.03},
    'CSCC': {'aht': 538, 'asa': 220, 'abn': 0.10},
    'Billing/Disputes': {'aht': 538, 'asa': 220, 'abn': 0.10},
    'TNC Billing and Dispute': {'aht': 538, 'asa': 220, 'abn': 0.10},
    'Damage': {'aht': 540, 'asa': 19, 'abn': 0.03},
    'Rental Extensions': {'aht': 331, 'asa': 140, 'abn': 0.03},
    'TNC Rental Extension': {'aht': 331, 'asa': 140, 'abn': 0.03},
    'MultiMonth': {'aht': 414, 'asa': 363, 'abn': 0.03},
    'Vehicle Control': {'aht': 345, 'asa': 53, 'abn': 0.10},
    'Roadside Services': {'aht': 700, 'asa': 258, 'abn': 0.14},
    'Languages': {'aht': 369, 'asa': 120, 'abn': 0.03},
    'FNOL': {'aht': 273, 'asa': 182, 'abn': 0.03},
    'CONFO': {'aht': 377, 'asa': 5, 'abn': 0.03},
    'First Choice Offered': {'aht': 252, 'asa': 19, 'abn': 0.02},
    'Executive Customer Services': {'aht': 448, 'asa': 22, 'abn': 0.02},
    'HRD': {'aht': 277, 'asa': 9, 'abn': 0.03},
    'Fleet Desk': {'aht': 385, 'asa': 19, 'abn': 0.02},
    'SPOC': {'aht': 229, 'asa': 10, 'abn': 0.02},
    'BRST': {'aht': 143, 'asa': 10, 'abn': 0.10},
    'Roadside Lite': {'aht': 605, 'asa': 10, 'abn': 0.06},
}

DEFAULT_TARGET = {'aht': 400, 'asa': 30, 'abn': 0.05}

LOB_DISPLAY_ORDER = [
    'Sales', 'CCM', 'Rental Extensions', 'TNC Rental Extension',
    'Roadside Services', 'International',
    'FNOL', 'HRD', 'Vehicle Control', 'Fleet Desk', 'Languages', 'MultiMonth',
    'SPOC', 'BRST', 'Executive Customer Services', 'Damage', 'CONFO',
    'Billing/Disputes', 'TNC Billing and Dispute', 'First Choice Offered', 'Roadside Lite', 'OPERATIONS',
]

VENDORS = ['TELUS', 'VXI', 'ATAIN', 'HERTZ']
