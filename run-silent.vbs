' ToolBox - silent launcher for Windows desktop shortcuts
'
' Uses pythonw so no console window appears, making the toolbox look like an
' ordinary desktop application.
'
' Double-clicking starts the background service: no console window, no browser
' window. Open http://127.0.0.1:8765 in your browser (bookmark it) and it is
' there. A message box appears only when start-up failed.

Option Explicit

Dim shell, fso, base, target, cmd, rc

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

base = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = base

target = base & "\src\main.py"

If Not fso.FileExists(target) Then
    MsgBox "Cannot find " & target, vbCritical, "ToolBox"
    WScript.Quit 1
End If

cmd = "pythonw """ & target & """ --detach"
' 2nd arg 0 = hidden window. 3rd arg True = wait for the exit code, which is
' safe because the launcher returns as soon as the service is up.
rc = shell.Run(cmd, 0, True)

If rc <> 0 Then
    MsgBox "ToolBox failed to start (code " & rc & ")." & vbCrLf & vbCrLf & _
           "Make sure port 8765 is free, or run run.bat to see the details.", _
           vbExclamation, "ToolBox"
End If

WScript.Quit rc
