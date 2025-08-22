// popup.js
// make buttons functional

document.addEventListener('DOMContentLoaded', () => {
    const startButton = document.getElementById('start'); // iniitate recording button
    const stopButton = document.getElementById('stop'); // terminate recording button
    const downloadButton = document.getElementById('download'); // download the action trace
    const status = document.getElementById('status'); // keep track of the status of recording across different webpages

    startButton.addEventListener('click', async ()=> {
        // Get the active tab
        const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
        
        // Send message to content script
        chrome.tabs.sendMessage(tab.id, {
            action: 'startRecording'
        }, (response) => {
            if (response) {
                console.log('Start recording response:', response);
                status.textContent = 'Recording...';
            }
        });
    });

    stopButton.addEventListener('click', async ()=> {
        const [tab] = await chrome.tabs.query({active: true, currentWindow: true});

        chrome.tabs.sendMessage(tab.id, {
            action: 'stopRecording'
        }, (response) => {
            if (response) {
                console.log('Stop recording response:', response);
                status.textContent = 'Stopped';
            }
        })
    });

    downloadButton.addEventListener('click', async ()=> {
        const [tab] = await chrome.tabs.query({active: true, currentWindow: true});

        chrome.tabs.sendMessage(tab.id, {
            action: 'downloadActionTrace'
        }, (response) => {
            if (response) {
                console.log('Download response:', response);
            }
        })
    });
});