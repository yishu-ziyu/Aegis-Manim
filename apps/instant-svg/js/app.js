(() => {
  'use strict';

  const STORAGE_KEY = 'aegis_settings_v2';
  const REQUEST_TIMEOUT_MS = 45000;

  const SYSTEM_PROMPT = `You are an expert SVG animator and educational content creator. Generate animated SVG code for educational concepts.

## Requirements
- Output ONLY valid SVG code (no markdown, no explanation)
- Use viewBox="0 0 800 600" for responsive sizing
- Include xmlns="http://www.w3.org/2000/svg"

## Animation Techniques (MUST use at least one)
1. SVG SMIL: <animate>, <animateTransform>
2. CSS @keyframes in <style> tags
3. stroke-dasharray/stroke-dashoffset for drawing effects

## Style
- Background: #1a1a2e (dark)
- Primary: #4f46e5 (indigo)
- Accent: #22d3ee (cyan)
- Text: #e2e8f0
- Font: 'Inter', system-ui, sans-serif

## Animation Principles
- Duration: 2-4 seconds
- Use ease-in-out timing
- repeatCount="indefinite" for loops
- Stagger animations by 0.2-0.5s

Output ONLY the <svg>...</svg> code, nothing else.`;

  const TEMPLATES = {
    math: {
      topic: '二次函数 y = x²',
      desc: '展示抛物线图像，动态标注顶点 (0,0)，使用深色背景和紫色曲线，曲线要有绘制动画',
    },
    neural: {
      topic: '人工神经网络结构',
      desc: '展示3层神经网络：输入层3个节点，隐藏层4个节点，输出层1个节点，用连线表示权重，有数据流动动画',
    },
    physics: {
      topic: '动量守恒定律',
      desc: '两个小球碰撞：左边红球向右移动撞击静止的蓝球，碰撞后蓝球向右移动，红球停止，展示动量传递',
    },
    timeline: {
      topic: '人工智能发展史',
      desc: '水平时间轴从1956到2024，标注：1956达特茅斯、1997深蓝、2016AlphaGo、2022ChatGPT，节点依次点亮',
    },
    'supply-demand': {
      topic: '微观经济学：供需曲线',
      desc: '展示市场均衡：向右下倾斜的红色需求曲线(D)，向右上倾斜的绿色供给曲线(S)，两曲线交于均衡点E。用虚线标注均衡价格P*和均衡数量Q*，曲线要有绘制动画，均衡点要有脉动效果',
    },
    'cost-curves': {
      topic: '微观经济学：成本曲线',
      desc: '展示厂商成本曲线：U型的红色边际成本曲线(MC)、U型的绿色平均总成本曲线(ATC)、U型的蓝色平均可变成本曲线(AVC)、递减的紫色平均固定成本曲线(AFC)。MC穿过ATC和AVC的最低点，标注交点',
    },
    'is-lm': {
      topic: '宏观经济学：IS-LM 模型',
      desc: '展示产品市场和货币市场均衡：向右下倾斜的红色IS曲线(产品市场)，向右上倾斜的绿色LM曲线(货币市场)，交于均衡点E。横轴为国民收入Y，纵轴为利率r，标注均衡利率r*和均衡收入Y*',
    },
    'ad-as': {
      topic: '宏观经济学：AD-AS 模型',
      desc: '展示总需求总供给模型：向右下倾斜的蓝色总需求曲线(AD)，垂直的红色长期总供给曲线(LRAS)，向右上倾斜的橙色短期总供给曲线(SRAS)。横轴为实际GDP(Y)，纵轴为价格水平(P)，标注长期均衡点',
    },
  };

  const STYLE_HINTS = {
    manim: '使用 Manim 动画风格：科学可视化，精确的坐标系，优雅的曲线动画',
    timeline: '使用时间轴风格：水平或垂直轴，节点依次点亮，清晰的日期标注',
    minimal: '使用极简风格：简洁线条，单色调，少量动画',
    artistic: '使用艺术风格：渐变色彩，流畅曲线，富有美感',
  };

  const FORBIDDEN_TAGS = new Set([
    'script',
    'iframe',
    'object',
    'embed',
    'foreignobject',
    'audio',
    'video',
    'canvas',
    'link',
    'meta',
  ]);

  const elements = {
    topicInput: document.getElementById('topic-input'),
    descInput: document.getElementById('desc-input'),
    generateBtn: document.getElementById('generate-btn'),
    svgCanvas: document.getElementById('svg-canvas'),
    svgRender: document.getElementById('svg-render'),
    svgPlaceholder: document.getElementById('svg-placeholder'),
    svgLoading: document.getElementById('svg-loading'),
    loadingText: document.getElementById('loading-text'),
    errorMsg: document.getElementById('error-msg'),
    styleButtons: document.querySelectorAll('[data-style]'),
    templateButtons: document.querySelectorAll('.template-btn'),
    viewCodeBtn: document.getElementById('view-code-btn'),
    downloadBtn: document.getElementById('download-btn'),
    fullscreenBtn: document.getElementById('fullscreen-btn'),
    codeModal: document.getElementById('code-modal'),
    closeModalBtn: document.getElementById('close-modal-btn'),
    codeEditor: document.getElementById('code-editor'),
    copyCodeBtn: document.getElementById('copy-code-btn'),
    applyCodeBtn: document.getElementById('apply-code-btn'),
    settingsBtn: document.getElementById('settings-btn'),
    settingsModal: document.getElementById('settings-modal'),
    closeSettingsBtn: document.getElementById('close-settings-btn'),
    apiProvider: document.getElementById('api-provider'),
    zhipuConfig: document.getElementById('zhipu-config'),
    nvidiaConfig: document.getElementById('nvidia-config'),
    zhipuKey: document.getElementById('zhipu-key'),
    nvidiaKey: document.getElementById('nvidia-key'),
    nvidiaModel: document.getElementById('nvidia-model'),
    saveSettingsBtn: document.getElementById('save-settings-btn'),
    statusDot: document.getElementById('status-dot'),
    statusText: document.getElementById('status-text'),
  };

  let currentStyle = 'manim';
  let currentSvgCode = '';

  function parseJSONSafe(raw, fallback) {
    try {
      return JSON.parse(raw);
    } catch {
      return fallback;
    }
  }

  function getSettings() {
    const stored = parseJSONSafe(localStorage.getItem(STORAGE_KEY) || '{}', {});
    return {
      provider: stored.provider === 'nvidia' ? 'nvidia' : 'zhipu',
      zhipuKey: typeof stored.zhipuKey === 'string' ? stored.zhipuKey.trim() : '',
      nvidiaKey: typeof stored.nvidiaKey === 'string' ? stored.nvidiaKey.trim() : '',
      nvidiaModel: typeof stored.nvidiaModel === 'string' && stored.nvidiaModel.trim()
        ? stored.nvidiaModel.trim()
        : 'z-ai/glm4.7',
    };
  }

  function persistSettings(settings) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
  }

  function getActiveApiKey(settings) {
    return settings.provider === 'zhipu' ? settings.zhipuKey : settings.nvidiaKey;
  }

  function updateStatus() {
    const settings = getSettings();
    const activeKey = getActiveApiKey(settings);

    if (activeKey) {
      elements.statusDot.className = 'status-dot connected';
      elements.statusText.textContent = settings.provider === 'zhipu' ? 'GLM 已就绪' : 'NVIDIA 已就绪';
      return;
    }

    elements.statusDot.className = 'status-dot idle';
    elements.statusText.textContent = '未配置';
  }

  function toggleProviderConfig() {
    const provider = elements.apiProvider.value;
    elements.zhipuConfig.classList.toggle('hidden', provider !== 'zhipu');
    elements.nvidiaConfig.classList.toggle('hidden', provider !== 'nvidia');
  }

  function loadSettingsIntoUI() {
    const settings = getSettings();
    elements.apiProvider.value = settings.provider;
    elements.zhipuKey.value = settings.zhipuKey;
    elements.nvidiaKey.value = settings.nvidiaKey;
    elements.nvidiaModel.value = settings.nvidiaModel;
    toggleProviderConfig();
    updateStatus();
  }

  function saveSettingsFromUI() {
    const settings = {
      provider: elements.apiProvider.value === 'nvidia' ? 'nvidia' : 'zhipu',
      zhipuKey: elements.zhipuKey.value.trim(),
      nvidiaKey: elements.nvidiaKey.value.trim(),
      nvidiaModel: elements.nvidiaModel.value.trim() || 'z-ai/glm4.7',
    };

    persistSettings(settings);
    updateStatus();
    elements.settingsModal.classList.add('hidden');
  }

  function showError(message) {
    elements.errorMsg.textContent = `❌ ${message}`;
    elements.errorMsg.classList.remove('hidden');
  }

  function toUserMessage(error, fallback) {
    if (error?.name === 'AbortError') {
      return '请求超时，请稍后重试';
    }
    if (error?.message) {
      return error.message;
    }
    return fallback;
  }

  function clearError() {
    elements.errorMsg.textContent = '';
    elements.errorMsg.classList.add('hidden');
  }

  function setLoading(isLoading, text = '正在生成动画...') {
    elements.generateBtn.disabled = isLoading;
    elements.svgLoading.classList.toggle('hidden', !isLoading);
    elements.loadingText.textContent = text;

    if (isLoading) {
      elements.svgPlaceholder.classList.add('hidden');
      elements.svgRender.innerHTML = '';
      clearError();
    }
  }

  function extractSVG(text) {
    const svgMatch = text.match(/<svg[\s\S]*?<\/svg>/i);
    if (svgMatch) return svgMatch[0];

    const codeBlockMatch = text.match(/```(?:svg|xml)?\s*([\s\S]*?)```/i);
    if (!codeBlockMatch) return null;

    const innerSvgMatch = codeBlockMatch[1].match(/<svg[\s\S]*?<\/svg>/i);
    return innerSvgMatch ? innerSvgMatch[0] : null;
  }

  function hasDangerousUrl(value) {
    const normalized = value.trim().replace(/\s+/g, '').toLowerCase();
    return normalized.startsWith('javascript:') || normalized.startsWith('data:text/html');
  }

  function sanitizeSVG(svgMarkup) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(svgMarkup, 'image/svg+xml');

    if (doc.getElementsByTagName('parsererror').length > 0) {
      throw new Error('SVG 格式错误，无法解析');
    }

    const svg = doc.documentElement;
    if (!svg || svg.tagName.toLowerCase() !== 'svg') {
      throw new Error('响应内容不是有效 SVG');
    }

    const nodes = [svg];

    while (nodes.length > 0) {
      const node = nodes.pop();
      const tagName = node.tagName.toLowerCase();

      if (FORBIDDEN_TAGS.has(tagName)) {
        node.remove();
        continue;
      }

      const attributes = Array.from(node.attributes);
      for (const attr of attributes) {
        const name = attr.name.toLowerCase();
        const value = attr.value;

        if (name.startsWith('on')) {
          node.removeAttribute(attr.name);
          continue;
        }

        if ((name === 'href' || name === 'xlink:href') && hasDangerousUrl(value)) {
          node.removeAttribute(attr.name);
          continue;
        }

        if (name === 'style' && /expression\(|javascript:/i.test(value)) {
          node.removeAttribute(attr.name);
        }
      }

      for (const child of Array.from(node.children)) {
        nodes.push(child);
      }
    }

    return new XMLSerializer().serializeToString(svg);
  }

  function renderSVG(svgMarkup) {
    const sanitized = sanitizeSVG(svgMarkup);
    currentSvgCode = sanitized;
    elements.svgRender.innerHTML = sanitized;
    elements.svgPlaceholder.classList.add('hidden');
  }

  async function fetchWithTimeout(url, options) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    try {
      return await fetch(url, { ...options, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
  }

  async function callZhipuAPI(prompt, settings) {
    const response = await fetchWithTimeout('https://open.bigmodel.cn/api/paas/v4/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${settings.zhipuKey}`,
      },
      body: JSON.stringify({
        model: 'glm-4.7-flash',
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: prompt },
        ],
        max_tokens: 8192,
        temperature: 0.7,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error?.message || `API 错误: ${response.status}`);
    }

    const content = data?.choices?.[0]?.message?.content;
    if (!content || typeof content !== 'string') {
      throw new Error('模型返回内容为空');
    }

    return content;
  }

  async function callNvidiaAPI(prompt, settings) {
    const response = await fetchWithTimeout('https://integrate.api.nvidia.com/v1/chat/completions', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${settings.nvidiaKey}`,
      },
      body: JSON.stringify({
        model: settings.nvidiaModel || 'z-ai/glm4.7',
        messages: [
          { role: 'system', content: SYSTEM_PROMPT },
          { role: 'user', content: prompt },
        ],
        max_tokens: 8192,
        temperature: 0.7,
      }),
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(data.error?.message || `API 错误: ${response.status}`);
    }

    const content = data?.choices?.[0]?.message?.content;
    if (!content || typeof content !== 'string') {
      throw new Error('模型返回内容为空');
    }

    return content;
  }

  async function callAPI(prompt) {
    const settings = getSettings();

    if (!getActiveApiKey(settings)) {
      throw new Error('请先在“API 设置”中配置当前提供商的 Key');
    }

    if (settings.provider === 'nvidia') {
      return callNvidiaAPI(prompt, settings);
    }

    return callZhipuAPI(prompt, settings);
  }

  function buildPrompt(topic, desc) {
    return `生成一个关于"${topic}"的教学动画 SVG。
${desc ? `详细要求：${desc}` : ''}
风格要求：${STYLE_HINTS[currentStyle] || ''}

请直接输出 SVG 代码，不要任何解释。`;
  }

  async function handleGenerate() {
    const topic = elements.topicInput.value.trim();
    if (!topic) {
      alert('请输入教学主题');
      return;
    }

    const desc = elements.descInput.value.trim();
    setLoading(true);

    try {
      const result = await callAPI(buildPrompt(topic, desc));
      const extracted = extractSVG(result);

      if (!extracted) {
        throw new Error('未能从响应中提取有效的 SVG 代码');
      }

      renderSVG(extracted);
    } catch (error) {
      elements.svgPlaceholder.classList.remove('hidden');
      showError(toUserMessage(error, '生成失败'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  }

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(elements.codeEditor.value);
      elements.copyCodeBtn.textContent = '✅ 已复制!';
      setTimeout(() => {
        elements.copyCodeBtn.textContent = '📋 复制代码';
      }, 2000);
    } catch {
      elements.codeEditor.select();
      document.execCommand('copy');
    }
  }

  function applyEditedCode() {
    try {
      renderSVG(elements.codeEditor.value);
      elements.codeModal.classList.add('hidden');
      clearError();
    } catch (error) {
      showError(toUserMessage(error, '应用代码失败'));
    }
  }

  function downloadCurrentSvg() {
    if (!currentSvgCode) {
      alert('请先生成 SVG');
      return;
    }

    const blob = new Blob([currentSvgCode], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'aegis-animation.svg';
    link.click();
    URL.revokeObjectURL(url);
  }

  function wireEvents() {
    for (const button of elements.styleButtons) {
      button.addEventListener('click', () => {
        for (const b of elements.styleButtons) {
          b.classList.remove('active');
        }
        button.classList.add('active');
        currentStyle = button.dataset.style || 'manim';
      });
    }

    for (const button of elements.templateButtons) {
      button.addEventListener('click', () => {
        const template = TEMPLATES[button.dataset.template];
        if (!template) return;
        elements.topicInput.value = template.topic;
        elements.descInput.value = template.desc;
      });
    }

    elements.generateBtn.addEventListener('click', handleGenerate);
    elements.settingsBtn.addEventListener('click', () => elements.settingsModal.classList.remove('hidden'));
    elements.closeSettingsBtn.addEventListener('click', () => elements.settingsModal.classList.add('hidden'));
    elements.settingsModal.addEventListener('click', (event) => {
      if (event.target === elements.settingsModal) {
        elements.settingsModal.classList.add('hidden');
      }
    });

    elements.apiProvider.addEventListener('change', () => {
      toggleProviderConfig();
      updateStatus();
    });

    elements.saveSettingsBtn.addEventListener('click', saveSettingsFromUI);

    elements.viewCodeBtn.addEventListener('click', () => {
      if (!currentSvgCode) {
        alert('请先生成 SVG');
        return;
      }
      elements.codeEditor.value = currentSvgCode;
      elements.codeModal.classList.remove('hidden');
    });

    elements.closeModalBtn.addEventListener('click', () => elements.codeModal.classList.add('hidden'));
    elements.codeModal.addEventListener('click', (event) => {
      if (event.target === elements.codeModal) {
        elements.codeModal.classList.add('hidden');
      }
    });

    elements.copyCodeBtn.addEventListener('click', copyCode);
    elements.applyCodeBtn.addEventListener('click', applyEditedCode);
    elements.downloadBtn.addEventListener('click', downloadCurrentSvg);

    elements.fullscreenBtn.addEventListener('click', () => {
      if (elements.svgCanvas.requestFullscreen) {
        elements.svgCanvas.requestFullscreen();
      }
    });
  }

  function bootstrap() {
    loadSettingsIntoUI();
    wireEvents();
  }

  bootstrap();
})();
