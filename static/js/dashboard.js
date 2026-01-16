// Sidebar Toggle
function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    
    sidebar.classList.toggle('collapsed');
    mainContent.classList.toggle('expanded');
    
    // Save state to localStorage
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebarCollapsed', isCollapsed);
}

// Initialize sidebar state
document.addEventListener('DOMContentLoaded', function() {
    const sidebar = document.getElementById('sidebar');
    const mainContent = document.getElementById('mainContent');
    
    const savedState = localStorage.getItem('sidebarCollapsed');
    if (savedState === 'true') {
        sidebar.classList.add('collapsed');
        mainContent.classList.add('expanded');
    }
    
    // Auto-collapse on mobile
    if (window.innerWidth < 768) {
        sidebar.classList.add('collapsed');
        mainContent.classList.add('expanded');
    }
});

// Confirm Delete Actions
function confirmDelete(action, itemName) {
    return confirm(`Are you sure you want to delete ${itemName}? This action cannot be undone.`);
}

// Format Currency
function formatCurrency(amount) {
    return 'KES ' + parseFloat(amount).toLocaleString('en-KE', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

// Auto-calculate total price
function calculateTotalPrice(priceInput, quantityInput, totalDisplay) {
    const price = parseFloat(priceInput.value) || 0;
    const quantity = parseInt(quantityInput.value) || 1;
    const total = price * quantity;
    
    if (totalDisplay) {
        totalDisplay.textContent = formatCurrency(total);
    }
    
    return total;
}

// Date Range Picker for Reports
function initDateRangePicker() {
    const today = new Date();
    const oneMonthAgo = new Date();
    oneMonthAgo.setMonth(today.getMonth() - 1);
    
    const dateRangeInput = document.getElementById('dateRange');
    if (dateRangeInput) {
        // You can integrate a proper date range picker library here
        // For now, we'll set default values
        dateRangeInput.value = 
            oneMonthAgo.toISOString().split('T')[0] + ' to ' + 
            today.toISOString().split('T')[0];
    }
}

// Chart Initialization Functions
function initProfitChart(ctx, data) {
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Profit (KES)',
                data: data.values,
                backgroundColor: 'rgba(74, 108, 247, 0.7)',
                borderColor: 'rgba(74, 108, 247, 1)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `KES ${context.raw.toLocaleString('en-KE')}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'KES ' + value.toLocaleString('en-KE');
                        }
                    }
                }
            }
        }
    });
}

function initTrendChart(ctx, data) {
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.labels,
            datasets: [{
                label: 'Daily Profit (KES)',
                data: data.values,
                borderColor: 'rgba(40, 167, 69, 1)',
                backgroundColor: 'rgba(40, 167, 69, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return `KES ${context.raw.toLocaleString('en-KE')}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function(value) {
                            return 'KES ' + value.toLocaleString('en-KE');
                        }
                    }
                }
            }
        }
    });
}

function initDistributionChart(ctx, data) {
    const colors = [
        '#4a6cf7', '#28a745', '#ffc107', '#dc3545', 
        '#17a2b8', '#6f42c1', '#fd7e14', '#20c997'
    ];
    
    return new Chart(ctx, {
        type: 'pie',
        data: {
            labels: data.labels,
            datasets: [{
                data: data.values,
                backgroundColor: colors,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.raw || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const percentage = Math.round((value / total) * 100);
                            return `${label}: ${value} units (${percentage}%)`;
                        }
                    }
                }
            }
        }
    });
}

// Initialize all charts on page load
document.addEventListener('DOMContentLoaded', function() {
    initDateRangePicker();
    
    // Initialize profit chart if element exists
    const profitChartCtx = document.getElementById('profitChart');
    if (profitChartCtx) {
        // You would typically fetch this data via AJAX or from template variables
        // For now, this is a placeholder
    }
    
    // Initialize trend chart if element exists
    const trendChartCtx = document.getElementById('trendChart');
    if (trendChartCtx) {
        // You would typically fetch this data via AJAX or from template variables
        // For now, this is a placeholder
    }
    
    // Initialize distribution chart if element exists
    const distributionChartCtx = document.getElementById('distributionChart');
    if (distributionChartCtx) {
        // You would typically fetch this data via AJAX or from template variables
        // For now, this is a placeholder
    }
});

// Export functionality
function exportToCSV(data, filename) {
    let csvContent = "data:text/csv;charset=utf-8,";
    
    // Add headers
    csvContent += Object.keys(data[0]).join(",") + "\n";
    
    // Add data rows
    data.forEach(item => {
        csvContent += Object.values(item).join(",") + "\n";
    });
    
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", filename + ".csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Print functionality
function printReport() {
    window.print();
}

// Mobile menu toggle for sidebar
document.addEventListener('DOMContentLoaded', function() {
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    if (sidebarToggle && window.innerWidth < 768) {
        sidebarToggle.style.display = 'block';
    }
});