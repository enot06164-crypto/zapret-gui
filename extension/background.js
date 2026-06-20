chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get(['apiHost'], (data) => {
    if (!data.apiHost) {
      chrome.storage.local.set({ apiHost: 'http://127.0.0.1:8080' });
    }
  });
});
