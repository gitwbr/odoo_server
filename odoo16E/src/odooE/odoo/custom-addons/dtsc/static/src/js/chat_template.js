odoo.define('dtsc.chart_dashboard_action', function (require) {
    "use strict";
    
    const { Component, onMounted } = require('@odoo/owl');
    const { registry } = require('@web/core/registry');

    class ChartDashboardAction extends Component {
        setup() {
            // 在组件挂载时执行的逻辑
            onMounted(() => {
                console.log('Chart Dashboard mounted');
                this.renderChart();
            });
        }

        renderChart() {
            // 在这里初始化和渲染你的图表
            console.log('Initializing chart...');
            // 你可以在这里添加 Chart.js 相关的代码来生成图表
        }
    }

    // 关联 QWeb 模板
    ChartDashboardAction.template = 'dtsc.chart_template';

    // 将组件注册为一个前端 client action
    registry.category('actions').add('chart_template_action', ChartDashboardAction);
});