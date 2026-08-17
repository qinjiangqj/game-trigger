(function() {
    var style = getComputedStyle(document.documentElement);
    var ink = style.getPropertyValue('--ink').trim();
    var accent = style.getPropertyValue('--accent').trim();
    var muted = style.getPropertyValue('--muted').trim();
    var rule = style.getPropertyValue('--rule').trim();
    var bg2 = style.getPropertyValue('--bg2').trim();

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
})();
