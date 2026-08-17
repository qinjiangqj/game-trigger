(function() {
    var style = getComputedStyle(document.documentElement);
    var accent = style.getPropertyValue('--accent').trim();
    var accent2 = style.getPropertyValue('--accent2').trim();
    var ink = style.getPropertyValue('--ink').trim();
    var muted = style.getPropertyValue('--muted').trim();
    var rule = style.getPropertyValue('--rule').trim();
    var bg2 = style.getPropertyValue('--bg2').trim();

    // ---------- Mermaid ----------
    if (window.mermaid) {
        mermaid.initialize({
            startOnLoad: true,
            theme: 'dark',
            securityLevel: 'loose',
            themeVariables: {
                primaryColor: '#232734',
                primaryTextColor: ink,
                primaryBorderColor: accent,
                secondaryColor: '#2a2e3d',
                tertiaryColor: bg2,
                lineColor: muted,
                textColor: ink,
                fontSize: '14px',
                clusterBkg: '#1a1d26',
                clusterBorder: rule,
                edgeLabelBackground: '#1c1f28'
            }
        });
    }

    var baseText = { color: muted, fontSize: 12 };
    var axisLine = { lineStyle: { color: rule } };

    // ---------- Chart 1: 选手性格参数 ----------
    var chartParams = echarts.init(document.getElementById('chart-params'), null, { renderer: 'svg' });
    chartParams.setOption({
        animation: false,
        tooltip: {
            trigger: 'axis',
            appendToBody: true,
            backgroundColor: '#1c1f28',
            borderColor: rule,
            textStyle: { color: ink, fontSize: 12 }
        },
        legend: {
            top: 0,
            textStyle: baseText,
            itemWidth: 14,
            itemHeight: 8
        },
        grid: { left: 8, right: 8, top: 40, bottom: 8, containLabel: true },
        xAxis: {
            type: 'category',
            data: ['Claude', 'GPT', 'Kimi', 'Gemini', 'GLM', 'DeepSeek'],
            axisLabel: { color: ink, fontSize: 12 },
            axisLine: axisLine,
            axisTick: { show: false }
        },
        yAxis: {
            type: 'value',
            max: 1,
            axisLabel: baseText,
            splitLine: { lineStyle: { color: rule, type: 'dashed' } }
        },
        series: [
            { name: 'R 攻击阈值', type: 'bar', barGap: 0.15, data: [0.16, 0.17, 0.20, 0.24, 0.28, 0.32], itemStyle: { color: accent2 }, barMaxWidth: 18 },
            { name: 'S 策略惯性', type: 'bar', data: [0.65, 0.50, 0.45, 0.30, 0.10, 0.15], itemStyle: { color: accent }, barMaxWidth: 18 },
            { name: 'C 冷静系数', type: 'bar', data: [0.75, 0.60, 0.40, 0.25, 0.15, 0.20], itemStyle: { color: accent + '88' }, barMaxWidth: 18 },
            { name: 'L 随机波动', type: 'bar', data: [0.02, 0.04, 0.08, 0.10, 0.18, 0.14], itemStyle: { color: muted }, barMaxWidth: 18 }
        ]
    });

    // ---------- Chart 2: 胜率 vs R ----------
    var chartResults = echarts.init(document.getElementById('chart-results'), null, { renderer: 'svg' });
    chartResults.setOption({
        animation: false,
        tooltip: {
            trigger: 'axis',
            appendToBody: true,
            backgroundColor: '#1c1f28',
            borderColor: rule,
            textStyle: { color: ink, fontSize: 12 },
            formatter: function(ps) {
                var html = '<b>' + ps[0].axisValue + '</b><br/>';
                ps.forEach(function(p) {
                    var v = p.seriesName === '胜率' ? p.value + '%' : p.value.toFixed(2);
                    html += p.marker + ' ' + p.seriesName + ': ' + v + '<br/>';
                });
                return html;
            }
        },
        legend: {
            top: 0,
            textStyle: baseText,
            itemWidth: 14,
            itemHeight: 8
        },
        grid: { left: 8, right: 8, top: 40, bottom: 8, containLabel: true },
        xAxis: {
            type: 'category',
            data: ['GPT', 'Claude', 'Kimi', 'GLM', 'Gemini', 'DeepSeek'],
            axisLabel: { color: ink, fontSize: 12 },
            axisLine: axisLine,
            axisTick: { show: false }
        },
        yAxis: [
            {
                type: 'value',
                min: 35,
                max: 60,
                axisLabel: { color: muted, fontSize: 12, formatter: '{value}%' },
                splitLine: { lineStyle: { color: rule, type: 'dashed' } }
            },
            {
                type: 'value',
                min: 0,
                max: 0.4,
                axisLabel: { color: muted, fontSize: 12 },
                splitLine: { show: false }
            }
        ],
        series: [
            {
                name: '胜率',
                type: 'bar',
                data: [54.6, 52.9, 52.9, 49.2, 48.8, 41.7],
                itemStyle: { color: accent },
                barMaxWidth: 34,
                label: { show: true, position: 'top', color: ink, fontSize: 11, formatter: '{c}%' }
            },
            {
                name: '攻击阈值 R',
                type: 'line',
                yAxisIndex: 1,
                data: [0.17, 0.16, 0.20, 0.28, 0.24, 0.32],
                symbol: 'circle',
                symbolSize: 8,
                lineStyle: { color: accent2, width: 2.5 },
                itemStyle: { color: accent2 }
            }
        ]
    });

    window.addEventListener('resize', function() {
        chartParams.resize();
        chartResults.resize();
    });
})();
