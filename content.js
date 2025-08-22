// content.js
// file used to perform function calls based on the user's actions in the chrome browser

function startRecording() {
    console.log('start recording');
}

function stopRecording() {
    console.log('stop recording');
}

function downloadActionTrace() {
    console.log('download action trace');
}


chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === 'startRecording') {
        startRecording();
        sendResponse({status: 'Recording started'});
    } else if (request.action === 'stopRecording') {
        stopRecording();
        sendResponse({status: 'Recording stopped'});
    } else if (request.action === 'downloadActionTrace') {
        downloadActionTrace();
    }

    return true;
})