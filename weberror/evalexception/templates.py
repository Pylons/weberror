error_template_layout = '''\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="en" lang="en">
<head>
 <title>Server Error</title>
 %(head)s

<!-- CSS Imports -->
<link rel="stylesheet" href="%(prefix)s/_debug/media/pylons/style/orange.css" type="text/css" media="screen" />

<!-- Favorite Icons -->
<link rel="icon" href="%(prefix)s/_debug/media/pylons/img/icon-16.png" type="image/png" />

<!-- Mako Styles -->
<style type="text/css">
    .stacktrace { margin:5px 5px 5px 5px; }
    .highlight { padding:0px 10px 0px 10px; background-color:#9F9FDF; }
    .nonhighlight { padding:0px; background-color:#DFDFDF; }
    .sample { padding:10px; margin:10px 10px 10px 10px; font-family:monospace; font-size: 110%%; }
    .sampleline { padding:0px 10px 0px 10px; }
    .sourceline { margin:5px 5px 10px 5px; font-family:monospace; font-size: 110%%;}
</style>

</head>

<body id="documentation" onload="switch_display('%(set_tab)s')">
<!-- We are only using a table to ensure old browsers see the message correctly -->

<noscript>
<div style="border-bottom: 1px solid #808080">
<div style="border-bottom: 1px solid #404040">
<table width="100%%" border="0" cellpadding="0" bgcolor="#FFFFE1"><tr><td valign="middle"><img src="%(prefix)s/_debug/media/pylons/img/warning.gif" alt="Warning" /></td><td>&nbsp;</td><td><span style="padding: 0px; margin: 0px; font-family: Tahoma, sans-serif; font-size: 11px">Warning, your browser does not support JavaScript so you will not be able to use the interactive debugging on this page.</span></td></tr></table>
</div>
</div>
</noscript>
    
    <!-- Top anchor -->
    <a name="top"></a>
    
    <!-- Logo -->
    <h1 id="logo"><a class="no-underline" href="http://pylonshq.com"><img class="no-border" src="%(prefix)s/_debug/media/pylons/img/logo.gif" alt="Pylons" title="Pylons"/></a></h1>
    <p class="invisible"><a href="#content">Skip to content</a></p>

    <!-- Main Content -->
    <div id="nav-bar">

        <!-- Section Navigation -->
        <h4 class="invisible">Section Links</h4>

            <ul id="navlist">
               <!--  %%(links)s -->
                <li id='traceback_data_tab' class="active"><a href="javascript:switch_display('traceback_data')" id='traceback_data_link' class="active"  accesskey="1">Traceback</a></li>
                <li id='extra_data_tab' class="" ><a href="javascript:switch_display('extra_data')" id='extra_data_link' accesskey="2" >Extra Data</a></li>
                <li id='template_data_tab'><a href="javascript:switch_display('template_data')" accesskey="3" id='template_data_link'>Template</a></li>
            </ul>
    </div>
    <div id="main-content">
        <div class="hr"><hr class="hr" /></div>
        <div class="content-padding">
            <div id="extra_data" class="hidden-data">
                %(extra_data)s
            </div>
            <div id="template_data" class="hidden-data">
                %(template_data)s
            </div>
            <div id="traceback_data">
                %(traceback_data)s
            </div>
        </div>
        <br class="clear" />
        <div class="hr"><hr class="clear" /></div>
        <!-- Footer -->
    </div>
    <div style=" background: #FFFF99; padding: 10px 10px 10px 6%%">
        The Pylons Team | 
        <a href="#top" accesskey="9" title="Return to the top of the navigation links">Top</a>
    </div>
</body>
</html>
'''

error_traceback_template = """\
<div style="float: left; width: 100%%; padding-bottom: 20px;">
<h1 class="first"><a name="content"></a>Error Traceback</h1>
<div id="error-area" style="display: none; background-color: #600; color: #fff; border: 2px solid black">
<button onclick="return clearError()">clear this</button>
<div id="error-container"></div>
<button onclick="return clearError()">clear this</button>
</div>
%(body)s
<br />
<div class="highlight" style="padding: 20px;">
<b>Extra Features</b>
<table border="0">
<tr><td>&gt;&gt;</td><td>Display the lines of code near each part of the traceback</td></tr>
<tr><td><img src="%(prefix)s/_debug/media/plus.jpg" /></td><td>Show a debug prompt to allow you to directly debug the code at the traceback</td></tr>
</table>
</div>%(repost_button)s"""

error_template = '''
<html>
<head>
 <title>Server Error</title>
 %(head_html)s
</head>
<body>

<div id="error-area" style="display: none; background-color: #600; color: #fff; border: 2px solid black">
<div id="error-container"></div>
<button onclick="return clearError()">clear this</button>
</div>

%(repost_button)s

%(body)s

</body>
</html>
'''

error_head_template = """
<style type="text/css">
        .red {
            color:#FF0000;
        }
        .bold {
            font-weight: bold;
        }
</style>
<script type="text/javascript">

if (document.images)
{
  pic1= new Image(100,25); 
  pic1.src="%(prefix)s/_debug/media/pylons/img/tab-yellow.png"; 
}

function switch_display(id) {
    ids = ['extra_data', 'template_data', 'traceback_data']
    for (i in ids){
        part = ids[i] 
        var el = document.getElementById(part);
        el.className = "hidden-data";
        var el = document.getElementById(part+'_tab');
        el.className = "not-active";
        var el = document.getElementById(part+'_link');
        el.className = "not-active";
    }
    var el = document.getElementById(id);
    el.className = "active";
    var el = document.getElementById(id+'_link');
    el.className = "active";
    var el = document.getElementById(id+'_tab');
    el.className = "active";
}   
</script>
"""
