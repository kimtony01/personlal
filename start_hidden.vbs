' start_app.bat 을 콘솔 창 없이 실행 (시작프로그램 폴더에 바로가기를 두면 로그인 시 자동 실행)
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run """" & dir & "\start_app.bat""", 0, False
