function showFrame(anchor) {
    var tbid = anchor.getAttribute('tbid');
    var expanded = anchor.expanded;
    if (expanded) {
        hideElement(anchor.expandedElement);
        anchor.expanded = false;
        _swapImage(anchor);
        return false;
    }
    anchor.expanded = true;
    if (anchor.expandedElement) {
        showElement(anchor.expandedElement);
        _swapImage(anchor);
        $('debug_input_'+tbid).focus();
        return false;
    }
    var url = debug_base
        + '/show_frame?tbid=' + tbid
        + '&debugcount=' + debug_count;
    callbackXHR(url, null, function (data) {
                    var el = createElement('div');
                    anchor.parentNode.insertBefore(el, anchor.nextSibling);
                    el.innerHTML = data.responseText;
                    anchor.expandedElement = el;
                    _swapImage(anchor);
                    $('debug_input_'+tbid).focus();
                });
    return false;
}

function _swapImage(anchor) {
    var el = anchor.getElementsByTagName('IMG')[0];
    if (anchor.expanded) {
        var img = 'minus.jpg';
    } else {
        var img = 'plus.jpg';
    }
    el.src = debug_base + '/media/' + img;
}

function submitInput(button, tbid) {
    var input = $(button.getAttribute('input-from'));
    var output = $(button.getAttribute('output-to'));
    var url = debug_base
        + '/exec_input';
    var history = input.form.history;
    input.historyPosition = 0;
    if (! history) {
        history = input.form.history = [];
    }
    history.push(input.value);
    var vars = {
        tbid: tbid,
        debugcount: debug_count,
        input: input.value
    };
    showElement(output);
    callbackXHR(url, vars, function (data) {
        var result = data.responseText;
        output.innerHTML += result;
        input.value = '';
        input.focus();
    });
    return false;
}

function showError(msg) {
    var el = $('error-container');
    if (el.innerHTML) {
        el.innerHTML += '<hr noshade>\n' + msg;
    } else {
        el.innerHTML = msg;
    }
    showElement($('error-area'));
}

function clearError() {
    var el = $('error-container');
    el.innerHTML = '';
    hideElement($('error-area'));
}

function expandInput(button) {
    var input = button.form.elements.input;
    stdops = {
        name: 'input',
        style: 'width: 100%',
        autocomplete: 'off'
    };
    if (input.tagName == 'INPUT') {
        var newEl = createElement('textarea', stdops);
        var text = 'Contract';
    } else {
        stdops['type'] = 'text';
        stdops['onkeypress'] = 'upArrow(this)';
        var newEl = createElement('input', stdops);
        var text = 'Expand';
    }
    newEl.value = input.value;
    newEl.id = input.id;
    swapDOM(input, newEl);
    newEl.focus();
    button.value = text;
    return false;
}

function upArrow(input, event) {
    if (window.event) {
        event = window.event;
    }
    if (event.keyCode != 38 && event.keyCode != 40) {
        // not an up- or down-arrow
        return true;
    }
    var dir = event.keyCode == 38 ? 1 : -1;
    var history = input.form.history;
    if (! history) {
        history = input.form.history = [];
    }
    var pos = input.historyPosition || 0;
    if (! pos && dir == -1) {
        return true;
    }
    if (! pos && input.value) {
        history.push(input.value);
        pos = 1;
    }
    pos += dir;
    if (history.length-pos < 0) {
        pos = 1;
    }
    if (history.length-pos > history.length-1) {
        input.value = '';
        return true;
    }
    input.historyPosition = pos;
    var line = history[history.length-pos];
    input.value = line;
}

function expandLong(anchor) {
    var span = anchor;
    while (span) {
        if (span.style && span.style.display == 'none') {
            break;
        }
        span = span.nextSibling;
    }
    if (! span) {
        return false;
    }
    showElement(span);
    hideElement(anchor);
    return false;
}

function showElement(el) {
    el.style.display = '';
}

function hideElement(el) {
    el.style.display = 'none';
}

function createElement(tag, attrs /*, sub-elements...*/) {
    var el = document.createElement(tag);
    if (attrs) {
        for (var i in attrs) {
            el.setAttribute(i, attrs[i]);
        }
    }
    for (var i=2; i<arguments.length; i++) {
        var item = arguments[i];
        if (typeof item == 'string') {
            item = document.createTextNode(item);
        }
        el.appendChild(item);
    }
    return el;
}

function swapDOM(dest, src) {
    var parent = dest.parentNode;
    parent.replaceChild(src, dest);
    return src;
}


function getXMLHttpRequest() {
    /* Taken from MochiKit */
    var tryThese = [
        function () { return new XMLHttpRequest(); },
        function () { return new ActiveXObject('Msxml2.XMLHTTP'); },
        function () { return new ActiveXObject('Microsoft.XMLHTTP'); },
        function () { return new ActiveXObject('Msxml2.XMLHTTP.4.0'); }
        ];
    for (var i = 0; i < tryThese.length; i++) {
        var func = tryThese[i];
        try {
            return func();
        } catch (e) {
            // pass
        }
    }
}

function callbackXHR(url, data, callback) {
    var xhr = getXMLHttpRequest();
    xhr.onreadystatechange = function () {
        if (xhr.readyState == 4) {
            if (xhr.status == 200) {
                callback(xhr);
            } else {
                showError(xhr.responseText);
            }
        }
    };
    var method = data ? "POST" : "GET";
    xhr.open(method, url);
    if (data) {
        if (! (typeof data == 'string')) {
            var newData = '';
            for (var i in data) {
                if (newData) {
                    newData += '&';
                }
                newData += i + '=' + escape(data[i]);
            }
            data = newData;
        }
        xhr.setRequestHeader('content-type', 'application/x-www-form-urlencoded');
        xhr.send(data);
    } else {
        xhr.send(null);
    }
}

function $(elementId) {
    return document.getElementById(elementId);
}
