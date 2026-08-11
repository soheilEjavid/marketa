; MARKETA — offline Windows installer.
;
; Everything the shop needs travels inside this .exe: the embeddable Python
; runtime, every dependency wheel, the built interface. Nothing is downloaded
; at install time.
;
; The one structural decision worth knowing before reading further: the
; program and the shop's data live in different places on purpose.
;
;   $INSTDIR  (Program Files\MARKETA)     replaced wholesale by an update
;   $DataDir  (ProgramData\MARKETA)       database, .env, logs, backups —
;                                         never touched by an update, and
;                                         left behind by an uninstall
;
; That split is what makes "update my friend's copy" safe. The wizard asks
; for the admin account only on a first install; on an update it finds the
; existing database, skips that page, and runs the migration with a backup
; taken first.
;
; Built by installer/build.sh, which passes VERSION, PAYLOAD_DIR and DIST_DIR.

Unicode true

!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
; MUI2 does not pull this in, and the administrator-account page is built
; with it.
!include "nsDialogs.nsh"

!ifndef VERSION
  !define VERSION "0.0.0"
!endif
!ifndef PAYLOAD_DIR
  !error "PAYLOAD_DIR was not defined; build through installer/build.sh."
!endif
!ifndef DIST_DIR
  !define DIST_DIR "dist"
!endif

!define APP_NAME "MARKETA"
!define REG_APP "Software\${APP_NAME}"
!define REG_UNINSTALL "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"

Name "${APP_NAME} ${VERSION}"
BrandingText "${APP_NAME} ${VERSION}"
; Forward slashes throughout for paths that belong to the *build* machine:
; this is compiled by makensis on Linux, where a backslash is not a
; separator. Paths that belong to the installed machine keep backslashes.
OutFile "${DIST_DIR}/MARKETA-Setup-${VERSION}.exe"
InstallDir "$PROGRAMFILES64\${APP_NAME}"
InstallDirRegKey HKLM "${REG_APP}" "InstallDir"
; Program Files and ProgramData both need it, as does icacls.
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUnInstDetails show

Var DataDir
Var IsUpgrade
Var AdminUser
Var AdminName
Var AdminPassword
Var AdminPasswordConfirm
Var Dialog
Var FieldUser
Var FieldName
Var FieldPassword
Var FieldPasswordConfirm

; ── Pages ────────────────────────────────────────────────────────────────

!define MUI_ABORTWARNING
!define MUI_ICON "${NSISDIR}/Contrib/Graphics/Icons/modern-install.ico"
!define MUI_UNICON "${NSISDIR}/Contrib/Graphics/Icons/modern-uninstall.ico"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS

; Where the program goes.
!define MUI_PAGE_HEADER_TEXT "$(TEXT_ProgramDirHeader)"
!define MUI_DIRECTORYPAGE_TEXT_TOP "$(TEXT_ProgramDirTop)"
!insertmacro MUI_PAGE_DIRECTORY

; Where the shop's data goes — a separate page because this is the one
; directory an update must never overwrite.
!define MUI_PAGE_HEADER_TEXT "$(TEXT_DataDirHeader)"
!define MUI_DIRECTORYPAGE_TEXT_TOP "$(TEXT_DataDirTop)"
!define MUI_DIRECTORYPAGE_TEXT_DESTINATION "$(TEXT_DataDirLabel)"
!define MUI_DIRECTORYPAGE_VARIABLE $DataDir
!define MUI_PAGE_CUSTOMFUNCTION_LEAVE DataDirLeave
!insertmacro MUI_PAGE_DIRECTORY

Page custom AdminPageCreate AdminPageLeave

!insertmacro MUI_PAGE_INSTFILES

; Through wscript.exe deliberately: the finish page runs its target with
; CreateProcess, which cannot execute a .vbs on its own.
!define MUI_FINISHPAGE_RUN "$SYSDIR\wscript.exe"
; $\" and not a bare quote: MUI substitutes this straight into an Exec
; string, where an unescaped quote ends the argument early and Exec then
; complains about being handed two parameters.
!define MUI_FINISHPAGE_RUN_PARAMETERS '$\"$INSTDIR\MARKETA.vbs$\"'
!define MUI_FINISHPAGE_RUN_TEXT "$(TEXT_FinishRun)"
!define MUI_FINISHPAGE_NOREBOOTSUPPORT
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

; Farsi first, so it is the default for the shop this is built for.
!insertmacro MUI_LANGUAGE "Farsi"
!insertmacro MUI_LANGUAGE "English"

; ── Text ─────────────────────────────────────────────────────────────────

LangString TEXT_ProgramDirHeader ${LANG_FARSI} "محل نصب برنامه"
LangString TEXT_ProgramDirHeader ${LANG_ENGLISH} "Program location"
LangString TEXT_ProgramDirTop ${LANG_FARSI} "برنامهٔ ${APP_NAME} در این پوشه نصب می‌شود. هنگام به‌روزرسانی، محتوای این پوشه کامل جایگزین می‌شود."
LangString TEXT_ProgramDirTop ${LANG_ENGLISH} "${APP_NAME} will be installed here. An update replaces this folder's contents entirely."

LangString TEXT_DataDirHeader ${LANG_FARSI} "محل داده‌های فروشگاه"
LangString TEXT_DataDirHeader ${LANG_ENGLISH} "Shop data location"
LangString TEXT_DataDirTop ${LANG_FARSI} "پایگاه داده، تنظیمات، گزارش‌های خطا و پشتیبان‌ها در این پوشه نگه داشته می‌شوند. این پوشه جدا از برنامه است تا به‌روزرسانی و حتی حذف برنامه هیچ‌وقت به موجودی انبار و اطلاعات مشتریان دست نزند."
LangString TEXT_DataDirTop ${LANG_ENGLISH} "The database, settings, logs and backups are kept here. This folder is deliberately separate from the program so that updating — or even uninstalling — can never touch the shop's stock and customer records."
LangString TEXT_DataDirLabel ${LANG_FARSI} "پوشهٔ داده‌ها"
LangString TEXT_DataDirLabel ${LANG_ENGLISH} "Data folder"

LangString TEXT_AdminHeader ${LANG_FARSI} "حساب مدیر"
LangString TEXT_AdminHeader ${LANG_ENGLISH} "Administrator account"
LangString TEXT_AdminSubHeader ${LANG_FARSI} "نخستین حساب کاربری فروشگاه"
LangString TEXT_AdminSubHeader ${LANG_ENGLISH} "The shop's first user account"
LangString TEXT_AdminIntro ${LANG_FARSI} "پایگاه داده خالی نصب می‌شود و هیچ حساب پیش‌فرضی وجود ندارد. این حساب تنها راه ورود به برنامه است؛ رمز آن را جایی مطمئن نگه دارید."
LangString TEXT_AdminIntro ${LANG_ENGLISH} "The database is installed empty and there are no default accounts. This is the only way in — keep the password somewhere safe."
LangString TEXT_AdminUser ${LANG_FARSI} "نام کاربری"
LangString TEXT_AdminUser ${LANG_ENGLISH} "Username"
LangString TEXT_AdminName ${LANG_FARSI} "نام و نام خانوادگی"
LangString TEXT_AdminName ${LANG_ENGLISH} "Full name"
LangString TEXT_AdminPassword ${LANG_FARSI} "رمز عبور"
LangString TEXT_AdminPassword ${LANG_ENGLISH} "Password"
LangString TEXT_AdminPasswordConfirm ${LANG_FARSI} "تکرار رمز عبور"
LangString TEXT_AdminPasswordConfirm ${LANG_ENGLISH} "Confirm password"

LangString TEXT_ErrUserShort ${LANG_FARSI} "نام کاربری باید حداقل ۳ نویسه باشد."
LangString TEXT_ErrUserShort ${LANG_ENGLISH} "The username must be at least 3 characters."
LangString TEXT_ErrNameEmpty ${LANG_FARSI} "نام و نام خانوادگی را وارد کنید."
LangString TEXT_ErrNameEmpty ${LANG_ENGLISH} "Please enter a full name."
LangString TEXT_ErrPasswordShort ${LANG_FARSI} "رمز عبور باید حداقل ۸ نویسه باشد."
LangString TEXT_ErrPasswordShort ${LANG_ENGLISH} "The password must be at least 8 characters."
LangString TEXT_ErrPasswordMismatch ${LANG_FARSI} "دو رمز وارد‌شده یکسان نیستند."
LangString TEXT_ErrPasswordMismatch ${LANG_ENGLISH} "The two passwords do not match."
LangString TEXT_ErrDataInProgram ${LANG_FARSI} "پوشهٔ داده‌ها نباید داخل پوشهٔ برنامه باشد، وگرنه به‌روزرسانی بعدی داده‌های فروشگاه را پاک می‌کند. پوشهٔ دیگری انتخاب کنید."
LangString TEXT_ErrDataInProgram ${LANG_ENGLISH} "The data folder must not sit inside the program folder, or the next update would delete the shop's records. Please choose another folder."

LangString TEXT_FinishRun ${LANG_FARSI} "اجرای ${APP_NAME}"
LangString TEXT_FinishRun ${LANG_ENGLISH} "Run ${APP_NAME}"

LangString TEXT_SecMain ${LANG_FARSI} "برنامهٔ ${APP_NAME} (لازم)"
LangString TEXT_SecMain ${LANG_ENGLISH} "${APP_NAME} program (required)"
LangString TEXT_SecDesktop ${LANG_FARSI} "میان‌بر روی میزکار"
LangString TEXT_SecDesktop ${LANG_ENGLISH} "Desktop shortcut"
LangString TEXT_SecStartup ${LANG_FARSI} "اجرای خودکار هنگام روشن شدن ویندوز"
LangString TEXT_SecStartup ${LANG_ENGLISH} "Start automatically with Windows"

LangString TEXT_Stopping ${LANG_FARSI} "متوقف کردن نسخهٔ در حال اجرا…"
LangString TEXT_Stopping ${LANG_ENGLISH} "Stopping the running copy..."
LangString TEXT_Migrating ${LANG_FARSI} "آماده‌سازی پایگاه داده (پشتیبان‌گیری پیش از تغییر)…"
LangString TEXT_Migrating ${LANG_ENGLISH} "Preparing the database (backing up first)..."
LangString TEXT_MigrateFailed ${LANG_FARSI} "آماده‌سازی پایگاه داده ناموفق بود. پایگاه داده از پشتیبان بازگردانی شد و هیچ تغییری اعمال نشده است. گزارش خطا در پوشهٔ logs داخل پوشهٔ داده‌ها است."
LangString TEXT_MigrateFailed ${LANG_ENGLISH} "Preparing the database failed. It was restored from the backup and nothing was changed. See the logs folder inside the data folder."
LangString TEXT_BootstrapFailed ${LANG_FARSI} "ساخت حساب مدیر ناموفق بود."
LangString TEXT_BootstrapFailed ${LANG_ENGLISH} "Creating the administrator account failed."

; ── Admin account page ───────────────────────────────────────────────────

Function AdminPageCreate
    ; An update already has its users; asking again would either be ignored
    ; or, worse, imply the old password had been replaced.
    ${If} $IsUpgrade == 1
        Abort
    ${EndIf}

    !insertmacro MUI_HEADER_TEXT "$(TEXT_AdminHeader)" "$(TEXT_AdminSubHeader)"
    nsDialogs::Create 1018
    Pop $Dialog
    ${If} $Dialog == error
        Abort
    ${EndIf}

    ${NSD_CreateLabel} 0 0 100% 26u "$(TEXT_AdminIntro)"
    Pop $0

    ${NSD_CreateLabel} 0 32u 30% 12u "$(TEXT_AdminUser)"
    Pop $0
    ${NSD_CreateText} 32% 30u 66% 13u "$AdminUser"
    Pop $FieldUser

    ${NSD_CreateLabel} 0 50u 30% 12u "$(TEXT_AdminName)"
    Pop $0
    ${NSD_CreateText} 32% 48u 66% 13u "$AdminName"
    Pop $FieldName

    ${NSD_CreateLabel} 0 68u 30% 12u "$(TEXT_AdminPassword)"
    Pop $0
    ${NSD_CreatePassword} 32% 66u 66% 13u "$AdminPassword"
    Pop $FieldPassword

    ${NSD_CreateLabel} 0 86u 30% 12u "$(TEXT_AdminPasswordConfirm)"
    Pop $0
    ${NSD_CreatePassword} 32% 84u 66% 13u "$AdminPasswordConfirm"
    Pop $FieldPasswordConfirm

    nsDialogs::Show
FunctionEnd

Function AdminPageLeave
    ${NSD_GetText} $FieldUser $AdminUser
    ${NSD_GetText} $FieldName $AdminName
    ${NSD_GetText} $FieldPassword $AdminPassword
    ${NSD_GetText} $FieldPasswordConfirm $AdminPasswordConfirm

    ; These bounds mirror backend/app/schemas/users.py::UserCreate. Checking
    ; here as well means the shopkeeper is told on the page rather than by a
    ; failure three steps into the install.
    StrLen $0 $AdminUser
    ${If} $0 < 3
        MessageBox MB_ICONEXCLAMATION|MB_OK "$(TEXT_ErrUserShort)"
        Abort
    ${EndIf}

    ${If} $AdminName == ""
        MessageBox MB_ICONEXCLAMATION|MB_OK "$(TEXT_ErrNameEmpty)"
        Abort
    ${EndIf}

    StrLen $0 $AdminPassword
    ${If} $0 < 8
        MessageBox MB_ICONEXCLAMATION|MB_OK "$(TEXT_ErrPasswordShort)"
        Abort
    ${EndIf}

    ${IfNot} $AdminPassword == $AdminPasswordConfirm
        MessageBox MB_ICONEXCLAMATION|MB_OK "$(TEXT_ErrPasswordMismatch)"
        Abort
    ${EndIf}
FunctionEnd

Function DataDirLeave
    ; A data folder nested inside the program folder would be destroyed by
    ; the RMDir /r that every update runs. This is the single most expensive
    ; mistake available on this page, so it is refused rather than warned about.
    ; Done with StrLen/StrCpy rather than StrFunc's ${StrLoc} to avoid that
    ; header's declare-before-use ritual for one comparison; StrCmp is
    ; case-insensitive, which is what Windows paths want anyway.
    StrLen $1 "$INSTDIR"
    StrCpy $0 "$DataDir" $1
    ${If} $0 == "$INSTDIR"
        MessageBox MB_ICONSTOP|MB_OK "$(TEXT_ErrDataInProgram)"
        Abort
    ${EndIf}

    ; An existing database here means this is an update, not a first install.
    ${If} ${FileExists} "$DataDir\marketa.db"
        StrCpy $IsUpgrade 1
    ${Else}
        StrCpy $IsUpgrade 0
    ${EndIf}
FunctionEnd

Function .onInit
    !insertmacro MUI_LANGDLL_DISPLAY
    ; All-users context: $APPDATA becomes ProgramData rather than one
    ; account's roaming folder, and the shortcuts below land on the shared
    ; Start Menu and desktop. A till is used by whoever is on shift, so the
    ; shop's data must not belong to the account that happened to install it.
    SetShellVarContext all
    ; Defaults, unless a previous install recorded its own choices. Resolved
    ; by Windows rather than assumed to be on C:, so a machine with Windows
    ; on another drive still works.
    StrCpy $DataDir "$APPDATA\${APP_NAME}"
    ReadRegStr $0 HKLM "${REG_APP}" "DataDir"
    ${If} $0 != ""
        StrCpy $DataDir $0
    ${EndIf}
    StrCpy $AdminUser "owner"
    StrCpy $IsUpgrade 0
FunctionEnd

; ── Install ──────────────────────────────────────────────────────────────

Section "$(TEXT_SecMain)" SecMain
    SectionIn RO

    ; Windows will not overwrite a .pyd or .exe that a running process holds
    ; open, so an update that skipped this would fail partway through copying.
    ${If} ${FileExists} "$INSTDIR\stop.py"
        DetailPrint "$(TEXT_Stopping)"
        nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\stop.py"'
        Pop $0
        Sleep 1500
    ${EndIf}

    ; The program folder is replaced wholesale: leftovers from an older
    ; version — a renamed module, a dependency no longer used — would sit on
    ; sys.path and get imported in preference to nothing at all.
    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\alembic"
    RMDir /r "$INSTDIR\python"

    SetOutPath "$INSTDIR"
    SetOverwrite on
    File /r "${PAYLOAD_DIR}/*"

    CreateDirectory "$DataDir"
    ; ProgramData subfolders created by an elevated installer inherit
    ; permissions that leave a standard user unable to write — and the shop's
    ; till account is usually a standard user. S-1-5-32-545 is the Users
    ; group by SID, which is the same on a Persian Windows as an English one.
    nsExec::ExecToLog 'icacls "$DataDir" /grant *S-1-5-32-545:(OI)(CI)M /T /C /Q'
    Pop $0

    ; configure.py records the data folder and writes .env on a first
    ; install; on an update it finds the file and leaves it — and with it the
    ; SECRET_KEY, the database path and the shop's clock settings.
    nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\configure.py" --data-dir "$DataDir"'
    Pop $0
    ${If} $0 != 0
        Abort "configure.py failed with code $0."
    ${EndIf}

    DetailPrint "$(TEXT_Migrating)"
    ${If} $IsUpgrade == 1
        nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\migrate.py"'
    ${Else}
        nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\migrate.py" --no-backup'
    ${EndIf}
    Pop $0
    ${If} $0 != 0
        ; migrate.py has already put the database back as it found it.
        MessageBox MB_ICONSTOP|MB_OK "$(TEXT_MigrateFailed)"
        Abort "migrate.py failed with code $0."
    ${EndIf}

    ${If} $IsUpgrade != 1
        ; The password goes through a file in $PLUGINSDIR — never on the
        ; command line, where any process on the machine can read it out of
        ; the process list. bootstrap.py deletes the file as it reads it, and
        ; $PLUGINSDIR is wiped when the installer exits either way.
        InitPluginsDir
        FileOpen $1 "$PLUGINSDIR\admin-password.txt" w
        FileWrite $1 "$AdminPassword"
        FileClose $1
        ; create_admin.py and not `-m app.bootstrap`: the wrapper makes the
        ; data directory the working directory first, which is where .env
        ; lives. Called directly, bootstrap starts in the program directory,
        ; finds no SECRET_KEY and dies in configuration validation.
        nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\create_admin.py" --username "$AdminUser" --full-name "$AdminName" --password-file "$PLUGINSDIR\admin-password.txt"'
        Pop $0
        Delete "$PLUGINSDIR\admin-password.txt"
        ${If} $0 != 0
            MessageBox MB_ICONSTOP|MB_OK "$(TEXT_BootstrapFailed)"
            Abort "app.bootstrap failed with code $0."
        ${EndIf}
    ${EndIf}

    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\MARKETA.vbs"
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Stop ${APP_NAME}.lnk" \
        "$INSTDIR\python\python.exe" '"$INSTDIR\stop.py"'
    CreateShortcut "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe"

    WriteRegStr HKLM "${REG_APP}" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "${REG_APP}" "DataDir" "$DataDir"
    WriteRegStr HKLM "${REG_APP}" "Version" "${VERSION}"

    WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKLM "${REG_UNINSTALL}" "DisplayVersion" "${VERSION}"
    WriteRegStr HKLM "${REG_UNINSTALL}" "Publisher" "${APP_NAME}"
    WriteRegStr HKLM "${REG_UNINSTALL}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKLM "${REG_UNINSTALL}" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKLM "${REG_UNINSTALL}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoModify" 1
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoRepair" 1
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "EstimatedSize" "$0"

    WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "$(TEXT_SecDesktop)" SecDesktop
    CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\MARKETA.vbs"
SectionEnd

Section /o "$(TEXT_SecStartup)" SecStartup
    CreateShortcut "$SMSTARTUP\${APP_NAME}.lnk" "$INSTDIR\MARKETA.vbs"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecMain} "$(TEXT_SecMain)"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} "$(TEXT_SecDesktop)"
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartup} "$(TEXT_SecStartup)"
!insertmacro MUI_FUNCTION_DESCRIPTION_END

; ── Uninstall ────────────────────────────────────────────────────────────

Function un.onInit
    !insertmacro MUI_UNGETLANGUAGE
    ; Must match the install context, or the uninstaller looks for the
    ; shortcuts in the installing user's own Start Menu and leaves the real
    ; ones behind.
    SetShellVarContext all
FunctionEnd

Section "Uninstall"
    ReadRegStr $DataDir HKLM "${REG_APP}" "DataDir"

    ${If} ${FileExists} "$INSTDIR\stop.py"
        nsExec::ExecToLog '"$INSTDIR\python\python.exe" "$INSTDIR\stop.py"'
        Pop $0
        Sleep 1500
    ${EndIf}

    Delete "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Stop ${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_NAME}\Uninstall ${APP_NAME}.lnk"
    RMDir "$SMPROGRAMS\${APP_NAME}"
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMSTARTUP\${APP_NAME}.lnk"

    RMDir /r "$INSTDIR\app"
    RMDir /r "$INSTDIR\alembic"
    RMDir /r "$INSTDIR\python"
    Delete "$INSTDIR\*.py"
    Delete "$INSTDIR\*.vbs"
    Delete "$INSTDIR\alembic.ini"
    Delete "$INSTDIR\data_dir.txt"
    Delete "$INSTDIR\uninstall.exe"
    RMDir "$INSTDIR"

    DeleteRegKey HKLM "${REG_UNINSTALL}"
    DeleteRegKey HKLM "${REG_APP}"

    ; $DataDir is deliberately left where it is. The shop's whole ledger —
    ; stock, customers, invoices, debts — is in there, and an uninstall is
    ; very often just the first half of a reinstall.
    ${If} $DataDir != ""
        DetailPrint "Shop data kept at $DataDir"
    ${EndIf}
SectionEnd
