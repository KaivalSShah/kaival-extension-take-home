// content.js
// file used to perform function calls based on the user's actions in the chrome browser

let isRecording = false;
let actionTrace = [];

// basic action types
const ACTION_TYPES = {
    CLICK: 'click',
    KEYBOARD: 'keyboard',
    NAVIGATE: 'navigate'
}

function getSelector(element) {
    if (element.id) return '#' + element.id;
    if (element.name) return `[name="${element.name}"]`;
    if (element.className) return '.' + element.className.split(' ')[0];
    return element.tagName.toLowerCase();
  }

function handleClick(event) {
    const element = event.target;
    actionTrace.push({
        type: ACTION_TYPES.CLICK,
        selector: getSelector(element),
        text: element.textContent?.substring(0, 50) || '',
        timestamp: Date.now()
    });
}

function handleKeyDown(event) {
    const element = event.target;

    actionTrace.push({
        type: ACTION_TYPES.KEYBOARD,
        selector: getSelector(element),
        key: event.key,
        code: event.code,
        ctrlKey: event.ctrlKey,
        shiftKey: event.shiftKey,
        altKey: event.altKey,
        metaKey: event.metaKey,
        timestamp: Date.now()
    });
}

function startRecording() {
    console.log('start recording');
    isRecording = true;
    actionTrace = [];

    actionTrace.push({
        type: ACTION_TYPES.NAVIGATE,
        url: window.location.href,
        timestamp: Date.now()
    });

    // listen for click events
    document.addEventListener('click', handleClick);
    document.addEventListener('keydown', handleKeyDown);
}

function stopRecording() {
    console.log('stop recording');
    isRecording = false;
    document.removeEventListener('click', handleClick);
    document.removeEventListener('keydown', handleKeyDown);

}

function downloadActionTrace() {
    console.log('download action trace');
    if (actionTrace.length === 0) {
        console.log('No action trace to download');
        return;
    }

    const blob = new Blob([JSON.stringify(actionTrace, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = 'action_trace.json';
    a.click();

}


chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'startRecording') {
        startRecording();
        sendResponse({ status: 'Recording started' });
    } else if (request.action === 'stopRecording') {
        stopRecording();
        sendResponse({ status: 'Recording stopped' });
    } else if (request.action === 'downloadActionTrace') {
        downloadActionTrace();
    }

    return true;
})