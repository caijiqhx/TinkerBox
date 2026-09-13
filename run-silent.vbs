' ToolBox - silent launcher for Windows desktop shortcuts
'
' Uses pythonw so no console window appears, making the toolbox look like an
' ordinary desktop application.
'
' Usage: right-click this file -> Send to -> Desktop (create shortcut),
'        then change the shortcut icon to assets\icon.ico if you like.

Option Explicit

Dim shell, fso, base, target, cmd

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
' second argument 0 = hidden window, third argument False = do not wait
shell.Run cmd, 0, False
