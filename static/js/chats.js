// Attach to file input
document.getElementById('fileInput').addEventListener('change', function() {
    const file = this.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    fetch('/api/chat/upload', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            // Store URL in a hidden field or variable
            window.pendingAttachment = data.file_url;
            // Optionally show preview
        } else {
            alert(data.message);
        }
    });
});

// When sending message, include window.pendingAttachment
function sendMessage() {
    const payload = {
        vendor_id: ...,
        message: document.getElementById('messageInput').value,
        attachment: window.pendingAttachment || ''
    };
    fetch('/api/customer/chat/send', { ... });
}