#!/bin/bash
#
# Verification script for Statistics Visualization implementation
#

echo "=========================================="
echo "Statistics Visualization - Verification"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass_count=0
fail_count=0

check_file() {
    local file=$1
    local description=$2

    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $description"
        ((pass_count++))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        ((fail_count++))
        return 1
    fi
}

check_content() {
    local file=$1
    local pattern=$2
    local description=$3

    if grep -q "$pattern" "$file" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} $description"
        ((pass_count++))
        return 0
    else
        echo -e "${RED}✗${NC} $description"
        ((fail_count++))
        return 1
    fi
}

echo "1. Checking Files Exist"
echo "------------------------"
check_file "web/index.html" "index.html exists"
check_file "web/css/styles.css" "styles.css exists"
check_file "web/js/main.js" "main.js exists"
check_file "web/js/statistics.js" "statistics.js exists (NEW)"
check_file "web/js/search.js" "search.js exists"
check_file "web/js/compare.js" "compare.js exists"
echo ""

echo "2. Checking HTML Structure"
echo "---------------------------"
check_content "web/index.html" "chart.js" "Chart.js CDN included"
check_content "web/index.html" "class=\"tabs\"" "Tab navigation added"
check_content "web/index.html" "id=\"casesTab\"" "Cases tab container"
check_content "web/index.html" "id=\"statisticsTab\"" "Statistics tab container"
check_content "web/index.html" "id=\"variableSelect\"" "Variable selector"
check_content "web/index.html" "id=\"metricSelect\"" "Metric selector"
check_content "web/index.html" "class=\"period-checkbox\"" "Period checkboxes"
check_content "web/index.html" "id=\"statisticsTable\"" "Statistics table"
check_content "web/index.html" "id=\"statisticsChart\"" "Statistics chart canvas"
check_content "web/index.html" "statistics.js" "statistics.js script tag"
echo ""

echo "3. Checking CSS Styles"
echo "----------------------"
check_content "web/css/styles.css" ".tabs" "Tab navigation styles"
check_content "web/css/styles.css" ".tab-btn" "Tab button styles"
check_content "web/css/styles.css" ".tab-content" "Tab content styles"
check_content "web/css/styles.css" ".statistics-controls" "Statistics controls styles"
check_content "web/css/styles.css" ".stats-table" "Statistics table styles"
check_content "web/css/styles.css" ".stats-chart-container" "Chart container styles"
check_content "web/css/styles.css" ".toggle-btn" "Toggle button styles"
check_content "web/css/styles.css" "@media.*768px" "Responsive breakpoints"
echo ""

echo "4. Checking JavaScript"
echo "----------------------"
check_content "web/js/main.js" "switchTab" "switchTab method added"
check_content "web/js/main.js" "statisticsManager" "statisticsManager property"
check_content "web/js/main.js" "StatisticsManager" "StatisticsManager instantiation"
check_content "web/js/statistics.js" "class StatisticsManager" "StatisticsManager class"
check_content "web/js/statistics.js" "discoverVariables" "discoverVariables method"
check_content "web/js/statistics.js" "aggregateData" "aggregateData method"
check_content "web/js/statistics.js" "renderTable" "renderTable method"
check_content "web/js/statistics.js" "renderChart" "renderChart method"
check_content "web/js/statistics.js" "Chart.js" "Chart.js integration"
echo ""

echo "5. Checking File Sizes"
echo "----------------------"
html_size=$(wc -c < web/index.html)
css_size=$(wc -c < web/css/styles.css)
js_size=$(wc -c < web/js/statistics.js)

echo "index.html:      $(numfmt --to=iec-i --suffix=B $html_size 2>/dev/null || echo "$html_size bytes")"
echo "styles.css:      $(numfmt --to=iec-i --suffix=B $css_size 2>/dev/null || echo "$css_size bytes")"
echo "statistics.js:   $(numfmt --to=iec-i --suffix=B $js_size 2>/dev/null || echo "$js_size bytes")"

if [ $html_size -gt 5000 ] && [ $html_size -lt 50000 ]; then
    echo -e "${GREEN}✓${NC} HTML size is reasonable"
    ((pass_count++))
else
    echo -e "${YELLOW}!${NC} HTML size may be unusual"
fi

if [ $css_size -gt 10000 ] && [ $css_size -lt 100000 ]; then
    echo -e "${GREEN}✓${NC} CSS size is reasonable"
    ((pass_count++))
else
    echo -e "${YELLOW}!${NC} CSS size may be unusual"
fi

if [ $js_size -gt 10000 ] && [ $js_size -lt 100000 ]; then
    echo -e "${GREEN}✓${NC} JavaScript size is reasonable"
    ((pass_count++))
else
    echo -e "${YELLOW}!${NC} JavaScript size may be unusual"
fi
echo ""

echo "6. Checking JavaScript Syntax"
echo "------------------------------"
if command -v node >/dev/null 2>&1; then
    if node --check web/js/statistics.js 2>/dev/null; then
        echo -e "${GREEN}✓${NC} statistics.js has valid syntax"
        ((pass_count++))
    else
        echo -e "${RED}✗${NC} statistics.js has syntax errors"
        ((fail_count++))
    fi

    if node --check web/js/main.js 2>/dev/null; then
        echo -e "${GREEN}✓${NC} main.js has valid syntax"
        ((pass_count++))
    else
        echo -e "${RED}✗${NC} main.js has syntax errors"
        ((fail_count++))
    fi
else
    echo -e "${YELLOW}!${NC} Node.js not available, skipping syntax check"
fi
echo ""

echo "7. Checking Documentation"
echo "-------------------------"
check_file "IMPLEMENTATION_SUMMARY.md" "Implementation summary"
check_file "NEXT_STEPS.md" "Next steps guide"
check_file "QUICKSTART.md" "Quick start guide"
echo ""

echo "=========================================="
echo "Results"
echo "=========================================="
echo -e "${GREEN}Passed: $pass_count${NC}"
echo -e "${RED}Failed: $fail_count${NC}"
echo ""

if [ $fail_count -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "Implementation is complete. Next steps:"
    echo "1. Run: python scripts/export_static.py"
    echo "2. Test: cd web && python -m http.server 8000"
    echo "3. Open: http://localhost:8000"
    echo "4. Click the 'Statistics' tab"
    echo ""
    echo "See NEXT_STEPS.md for detailed instructions."
    exit 0
else
    echo -e "${RED}Some checks failed. Please review the output above.${NC}"
    exit 1
fi
