// Funções auxiliares
function formatCurrency(value) {
    return new Intl.NumberFormat('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    }).format(value);
}

function showLoading() {
    const spinner = document.createElement('div');
    spinner.className = 'loading-spinner';
    spinner.innerHTML = '<div class="spinner-border text-primary" role="status"><span class="visually-hidden">Carregando...</span></div>';
    document.body.appendChild(spinner);
}

function hideLoading() {
    const spinner = document.querySelector('.loading-spinner');
    if (spinner) spinner.remove();
}

function initializeSidebarToggle() {
    const toggleButton = document.getElementById('sidebarToggle');
    if (!toggleButton) return;

    const label = toggleButton.querySelector('span');
    const icon = toggleButton.querySelector('i');
    const storageKey = 'sidebar_collapsed';

    const updateButton = (collapsed) => {
        if (label) label.textContent = collapsed ? 'Mostrar menu' : 'Ocultar menu';
        if (icon) {
            icon.className = collapsed
                ? 'bi bi-layout-sidebar'
                : 'bi bi-layout-sidebar-inset';
        }
        toggleButton.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    };

    const setCollapsed = (collapsed) => {
        document.body.classList.toggle('sidebar-collapsed', collapsed);
        localStorage.setItem(storageKey, collapsed ? '1' : '0');
        updateButton(collapsed);
    };

    const wasCollapsed = localStorage.getItem(storageKey) === '1';
    setCollapsed(wasCollapsed);

    toggleButton.addEventListener('click', () => {
        const collapsed = !document.body.classList.contains('sidebar-collapsed');
        setCollapsed(collapsed);
    });
}

// Confirmação de exclusão
function confirmDelete(message = 'Tem certeza que deseja excluir?') {
    return confirm(message);
}

// Auto-hide para alertas
document.addEventListener('DOMContentLoaded', function() {
    const alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease';
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 500);
        }, 5000);
    });

    initializeSidebarToggle();
});

// Calcular receita líquida automaticamente no formulário
document.addEventListener('DOMContentLoaded', function() {
    const form = document.querySelector('form');
    if (!form) return;
    
    const grossAmount = document.getElementById('gross_amount');
    const tipAmount = document.getElementById('tip_amount');
    const platformFee = document.getElementById('platform_fee');
    const tolls = document.getElementById('tolls');
    const parking = document.getElementById('parking');
    const fuelCost = document.getElementById('fuel_cost');
    const otherCosts = document.getElementById('other_costs');
    
    if (!grossAmount) return;
    
    function calculateNetRevenue() {
        const gross = parseFloat(grossAmount.value) || 0;
        const tip = parseFloat(tipAmount?.value || 0);
        const fee = parseFloat(platformFee?.value || 0);
        const toll = parseFloat(tolls?.value || 0);
        const park = parseFloat(parking?.value || 0);
        const fuel = parseFloat(fuelCost?.value || 0);
        const other = parseFloat(otherCosts?.value || 0);
        
        const total = gross + tip - fee - toll - park - fuel - other;
        
        const netDisplay = document.getElementById('net-revenue-display');
        if (netDisplay) {
            netDisplay.textContent = formatCurrency(total);
            netDisplay.className = total >= 0 ? 'text-success' : 'text-danger';
        }
    }
    
    [grossAmount, tipAmount, platformFee, tolls, parking, fuelCost, otherCosts].forEach(input => {
        if (input) input.addEventListener('input', calculateNetRevenue);
    });
});

// Filtros dinâmicos
document.addEventListener('DOMContentLoaded', function() {
    const filterForm = document.querySelector('.filter-form');
    if (!filterForm) return;
    
    const selects = filterForm.querySelectorAll('select');
    selects.forEach(select => {
        select.addEventListener('change', () => {
            showLoading();
            filterForm.submit();
        });
    });
});

// Inicialização de gráficos (Chart.js)
function initializeCharts() {
    // Paleta alinhada ao tema visual do produto.
    if (typeof Chart === 'undefined') return;

    Chart.defaults.font.family = "'Manrope', 'Segoe UI', sans-serif";
    Chart.defaults.color = '#5f6f8f';
    Chart.defaults.borderColor = 'rgba(155, 172, 193, 0.28)';
    Chart.defaults.elements.line.borderWidth = 3;
    Chart.defaults.elements.point.radius = 3;
    Chart.defaults.elements.point.hoverRadius = 5;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 9;
    Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(15, 23, 36, 0.94)';
    Chart.defaults.plugins.tooltip.titleColor = '#f8fafc';
    Chart.defaults.plugins.tooltip.bodyColor = '#d6e2f2';
    Chart.defaults.plugins.tooltip.borderColor = 'rgba(255, 122, 26, 0.35)';
    Chart.defaults.plugins.tooltip.borderWidth = 1;
    Chart.defaults.plugins.tooltip.padding = 12;
}

initializeCharts();

// Validação de formulários
document.addEventListener('DOMContentLoaded', function() {
    const forms = document.querySelectorAll('.needs-validation');
    Array.from(forms).forEach(form => {
        form.addEventListener('submit', event => {
            if (!form.checkValidity()) {
                event.preventDefault();
                event.stopPropagation();
            }
            form.classList.add('was-validated');
        }, false);
    });
});

// Máscara para CPF
function maskCPF(value) {
    return value
        .replace(/\D/g, '')
        .replace(/(\d{3})(\d)/, '$1.$2')
        .replace(/(\d{3})(\d)/, '$1.$2')
        .replace(/(\d{3})(\d{1,2})/, '$1-$2')
        .replace(/(-\d{2})\d+?$/, '$1');
}

// Máscara para telefone
function maskPhone(value) {
    return value
        .replace(/\D/g, '')
        .replace(/(\d{2})(\d)/, '($1) $2')
        .replace(/(\d{5})(\d)/, '$1-$2')
        .replace(/(-\d{4})\d+?$/, '$1');
}

// Aplicar máscaras
document.addEventListener('DOMContentLoaded', function() {
    const cpfInput = document.getElementById('cpf');
    if (cpfInput) {
        cpfInput.addEventListener('input', (e) => {
            e.target.value = maskCPF(e.target.value);
        });
    }
    
    const phoneInput = document.getElementById('phone');
    if (phoneInput) {
        phoneInput.addEventListener('input', (e) => {
            e.target.value = maskPhone(e.target.value);
        });
    }
});

// Tooltips do Bootstrap
document.addEventListener('DOMContentLoaded', function() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
});
