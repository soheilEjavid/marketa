' Starts MARKETA with no console window on screen.
'
' pythonw.exe is the windowless build of the interpreter, but launching it
' from a shortcut still flashes a console for an instant on some Windows
' versions; going through wscript with a window style of 0 suppresses that
' entirely. launch.py itself opens the browser once the server answers.

Option Explicit

Dim shell, fileSystem, appDir, pythonw, script

Set shell = CreateObject("WScript.Shell")
Set fileSystem = CreateObject("Scripting.FileSystemObject")

appDir = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonw = appDir & "\python\pythonw.exe"
script = appDir & "\launch.py"

If Not fileSystem.FileExists(pythonw) Then
    MsgBox "MARKETA is missing its Python runtime:" & vbCrLf & pythonw & _
           vbCrLf & vbCrLf & "Reinstall MARKETA to repair it.", 16, "MARKETA"
    WScript.Quit 1
End If

shell.CurrentDirectory = appDir
' 0 = hidden window, False = do not wait for it to exit.
shell.Run """" & pythonw & """ """ & script & """", 0, False
