import sublime, sublime_plugin
import COLT.colt, COLT.colt_rpc
import functools
import os.path
import json
import re

from COLT.colt import ColtPreferences, isColtFile
from COLT.colt_rpc import ColtConnection, isConnected, hasActiveSessions

def getWordPosition(view):
        position = getPosition(view)
        return view.word(position).end()

def getPosition(view):
        for sel in view.sel() :
                return sel

        return None

def getPositionEnd(view):
        position = getPosition(view)
        if position is None :
                return - 1

        return position.end()

def getContent(view):
        return view.substr(sublime.Region(0, view.size()))

def isAutosaveEnabled():
        settings = sublime.load_settings(ColtPreferences.NAME)
        return settings.get("autosave", False)

class ToggleAutosaveCommand(sublime_plugin.ApplicationCommand):
        def run(self):
                currentValue = isAutosaveEnabled()
                settings = sublime.load_settings(ColtPreferences.NAME)
                settings.set("autosave", not currentValue)
                sublime.save_settings(ColtPreferences.NAME)

        def description(self):
                if isAutosaveEnabled() :
                        return "Disable Autosave"
                else :
                        return "Enable Autosave"

class ColtAutosaveListener(sublime_plugin.EventListener):
        
        def on_modified(self, view):
                if isColtFile(view) and isConnected() and hasActiveSessions() and isAutosaveEnabled() :
                        view.run_command("save")


class ColtCompletitions(sublime_plugin.EventListener):
        
        def on_query_completions(self, view, prefix, locations):                
                if not isColtFile(view) :
                        return []

                position = getPositionEnd(view)

                if view.substr(position - 1) == "." :
                        position = position - 1
                else :
                        wordStart = view.word(getPosition(view)).begin()
                        if view.substr(wordStart - 1) == "." :
                                position = wordStart - 1
                        else :
                                return []

                if not isConnected() or not hasActiveSessions() :
                        return []

                response = COLT.colt_rpc.getContextForPosition(view.file_name(), position, getContent(view), "PROPERTIES")
                if "error" in response :
                        return []

                result = response["result"]
                completitions = []
                if not result is None :
                        resultJSON = json.loads(result)
                        for resultStr in resultJSON :
                                if "{})" in resultStr :
                                        resultStr = resultStr.replace("{})", "")

                                replaceStr = resultStr
                                displayStr = resultStr
                                cursiveStr = ""

                                if "(" in resultStr :
                                        replaceStr = resultStr[:resultStr.index("(")]
                                        displayStr = replaceStr
                                        cursiveStr = resultStr

                                completitions.append((displayStr + "\t" + cursiveStr + "[COLT]", replaceStr))

                return completitions

class AbstractColtRunCommand(sublime_plugin.WindowCommand):
        def run(self):
                return

        def getSettings(self):
                settings = sublime.load_settings(ColtPreferences.NAME)
                if not settings.has("coltPath") :                        
                        sublime.error_message("COLT path is not specified, please enter the path")
                        self.window.show_input_panel("COLT Path:", "", self.onCOLTPathInput, None, None)
                        return

                settings = sublime.load_settings(ColtPreferences.NAME)
                coltPath = settings.get("coltPath")
                
                if not os.path.exists(coltPath) :
                        sublime.error_message("COLT path specified is invalid, please enter the correct path")
                        self.window.show_input_panel("COLT Path:", "", self.onCOLTPathInput, None, None)
                        return

                return sublime.load_settings(ColtPreferences.NAME)    

        def onCOLTPathInput(self, inputPath):
                if inputPath and os.path.exists(inputPath) :
                        settings = sublime.load_settings(ColtPreferences.NAME)
                        settings.set("coltPath", inputPath)
                        sublime.save_settings(ColtPreferences.NAME)
                        self.run()
                else :
                        sublime.error_message("COLT path specified is invalid")   

        def is_enabled(self):
                if self.window.active_view() is None :
                        return False
                return isColtFile(self.window.active_view())

class GetAllCountsCommand(sublime_plugin.WindowCommand):
        ranges = []
    
        def run(self):
            # but 1st, clear every region this command could have created
            for p in GetAllCountsCommand.ranges:
                p[0].erase_regions(p[1])
                
            GetAllCountsCommand.ranges = []
                        
            if ColtConnection.activeSessions > 0:
                
                # getMethodCounts
                # {u'jsonrpc': u'2.0', u'id': 77, u'result': [{u'count': 1, u'position': 339, u'filePath': u'/Users/makc/Downloads/d3/bubles.js'}, ...
                resultJSON = COLT.colt_rpc.getMethodCounts()
                
                if ("error" in resultJSON) or resultJSON["result"] is None :
                        # sublime.error_message("Can't read method counts")
                        return
                        
                for info in resultJSON["result"]:

                    position = info["position"]
                    filePath = info["filePath"]
                                        
                    count = info["count"]
                    if count > 0:
                        if count > 9:
                            count = "infinity"
                    
                        for view in self.window.views():
                            if view.file_name() == filePath:
                                view.add_regions("counts." + str(position), [sublime.Region(position)],
                                    "scope", "Packages/COLT/icons/" + str(count) + "@2x.png", sublime.HIDDEN)
                                GetAllCountsCommand.ranges.append([view, "counts." + str(position)])

class ShowLastErrorCommand(sublime_plugin.WindowCommand):
    def run(self):
        # but 1st, clear every region this command could have created
        for view in self.window.views():
            view.erase_regions("error.colt")
                
        if ColtConnection.activeSessions > 0:
            resultJSON = COLT.colt_rpc.getLastRuntimeError();
                
            if ("error" in resultJSON) or resultJSON["result"] is None :
                # sublime.error_message("Can't read method counts")
                return
            
            for view in self.window.views():
                if view.file_name() == resultJSON["result"]["filePath"]:
                    position = resultJSON["result"]["position"]
                    view.erase_regions("counts." + str(position))
                    view.add_regions("error.colt", [sublime.Region(position)],
                        "scope", "Packages/COLT/icons/error@2x.png", sublime.HIDDEN)
                    

# ST3 version of http://www.sublimetext.com/docs/plugin-examples Idle Watcher
class IdleWatcher(sublime_plugin.EventListener):
    pending = 0
    ranges = []
    
    def handleTimeout(self, view):
        self.pending = self.pending - 1
        if self.pending == 0:
            # There are no more queued up calls to handleTimeout, so it must have
            # been 800ms since the last modification
            self.onIdle(view)

    def onModified(self, view):
        self.pending = self.pending + 1
        # Ask for handleTimeout to be called in 800ms
        sublime.set_timeout(functools.partial(self.handleTimeout, view), 800)

    def printLogs(self):
        if ColtConnection.activeSessions > 0:
            resultJSON = COLT.colt_rpc.getLastLogMessages()
            if ("error" in resultJSON) or resultJSON["result"] is None :
                return
            if len(resultJSON["result"]) > 0 :
                
                syntaxErrors = []
                
                for info in resultJSON["result"] :
                    if info["position"] > -1 :
                        # syntax error
                        if (len (info["message"]) == 0) :
                            # empty syntax error message signals that corresponding page was reloaded
                            for p in IdleWatcher.ranges:
                                if p[0].file_name() == info["filePath"]:
                                    p[0].erase_regions(p[1])
                                    IdleWatcher.ranges.remove(p)
                        else :
                            # add to the list and print
                            syntaxErrors.append(info)
                            print("[COLT] " + info["message"])
                    else :
                        # just print it
                        print("[COLT] " + info["message"])
                    
                # now show syntax errors
                for info in syntaxErrors :
                    for view in sublime.active_window().views():
                        if view.file_name() == info["filePath"]:
                            position = info["position"]
                            view.add_regions("error." + str(position), [sublime.Region(position)],
                                "scope", "Packages/COLT/icons/error@2x.png", sublime.HIDDEN)
                            IdleWatcher.ranges.append([view, "error." + str(position)])
                        
                    
                #sublime.active_window().run_command("show_panel", {"panel": "console", "toggle": False})
        else :
            # clear all ranges
            for p in IdleWatcher.ranges:
                p[0].erase_regions(p[1])
                
            IdleWatcher.ranges = []
                
    def onIdle(self, view):
        #print "No activity in the past 800ms"
        sublime.active_window().run_command("get_all_counts")
        sublime.active_window().run_command("show_last_error")
        self.printLogs()
        sublime.set_timeout(functools.partial(self.onModified, view), 800)

    def on_modified(self, view):
        self.onModified(view)

    def on_selection_modified(self, view):
        self.onModified(view)
    
    def on_activated(self, view):
        self.onModified(view)

                
class ColtGoToDeclarationCommand(sublime_plugin.WindowCommand):

        def run(self):
                view = self.window.active_view()

                fileName = view.file_name()
                position = getWordPosition(view)
                content = getContent(view)

                resultJSON = COLT.colt_rpc.getDeclarationPosition(fileName, position, content)
                if "error" in resultJSON or resultJSON["result"] is None :
                        # sublime.error_message("Can't find a declaration")
                        return

                position = resultJSON["result"]["position"]
                filePath = resultJSON["result"]["filePath"]

                targetView = self.window.open_file(filePath)
                targetView.sel().clear()
                targetView.sel().add(sublime.Region(position))
                
                targetView.show_at_center(position)
                
                # work around sublime bug with caret position not refreshing
                # does not seem to be reliable in ST3, need better method...
                bug = [s for s in targetView.sel()]
                targetView.add_regions("bug", bug, "bug", "dot", sublime.HIDDEN | sublime.PERSISTENT)
                targetView.erase_regions("bug")

        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isColtFile(view) and isConnected() and hasActiveSessions()

class ColtRunFunctionCommand(sublime_plugin.WindowCommand):

        def run(self):
                view = self.window.active_view()

                fileName = view.file_name()
                position = getWordPosition(view)
                content = getContent(view)
                
                methodId = COLT.colt_rpc.getMethodId(fileName, position, content)

                if methodId is None :
                        sublime.error_message("Can't figure out the function ID")
                        return

                if methodId.startswith('"') :
                        methodId = methodId[1:len(methodId)-1]

                COLT.colt_rpc.runMethod(methodId)
                
                self.window.run_command("get_all_counts")
        
        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isColtFile(view) and isConnected() and hasActiveSessions()
        
class ColtResetCallCountsCommand(sublime_plugin.WindowCommand):
        def run(self):
                COLT.colt_rpc.resetCallCounts()

                self.window.run_command("get_all_counts")

        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isColtFile(view) and isConnected() and hasActiveSessions()

class ColtViewCallCountCommand(sublime_plugin.WindowCommand):
        def run(self):
                view = self.window.active_view()

                outputPanel = self.window.get_output_panel("COLT")
                outputPanel.set_scratch(True)
                outputPanel.set_read_only(False)
                outputPanel.set_name("COLT")
                self.window.run_command("show_panel", {"panel": "output.COLT"})
                self.window.set_view_index(outputPanel, 1, 0)
                
                position = getWordPosition(view)
                resultJSON = COLT.colt_rpc.getCallCount(view.file_name(), position, getContent(view))

                if "result" in resultJSON :
                        position = getPosition(view)
                        word = view.word(position)

                        result = resultJSON["result"]
                        if result is None :
                                outputPanel.run_command("append_to_console", {"text": "Call count is not available"})
                        else :
                                outputPanel.run_command("append_to_console", {"text": "Call count: " + str(result)})

        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isColtFile(view) and isConnected() and hasActiveSessions()
                
# begin_end() and end_edit() are no longer accessible
# http://www.sublimetext.com/docs/3/porting_guide.html
class AppendToConsoleCommand(sublime_plugin.TextCommand):
        def run(self, edit, text):
                self.view.insert(edit, self.view.size(), text + '\n')
                self.view.show(self.view.size())
                
class ColtViewValueCommand(sublime_plugin.WindowCommand):
        def run(self):
                view = self.window.active_view()

                outputPanel = self.window.get_output_panel("COLT")
                outputPanel.set_scratch(True)
                outputPanel.set_read_only(False)
                outputPanel.set_name("COLT")
                self.window.run_command("show_panel", {"panel": "output.COLT"})
                self.window.set_view_index(outputPanel, 1, 0)
                
                position = getWordPosition(view)
                
                expression = None
                for sel in view.sel() :
                    if expression is None :
                        expression = view.substr(sel)
                
                resultJSON = COLT.colt_rpc.evaluateExpression(view.file_name(), expression, position, getContent(view))
                if "result" in resultJSON :
                        position = getPosition(view)
                        word = view.word(position)

                        result = resultJSON["result"]
                        if result is None :
                                outputPanel.run_command("append_to_console", {"text": view.substr(word) + " value: unknown"})
                        else :
                                outputPanel.run_command("append_to_console", {"text": result})

        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isColtFile(view) and isConnected() and hasActiveSessions()
        
class ColtReloadCommand(sublime_plugin.WindowCommand):
        def run(self):
                COLT.colt_rpc.reload()

        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isConnected() and hasActiveSessions()
class ColtClearLogCommand(sublime_plugin.WindowCommand):
        def run(self):
                COLT.colt_rpc.clearLog()

        def is_enabled(self):
                view = self.window.active_view()
                if view is None :
                        return False
                return isConnected() and hasActiveSessions()

class StartColtCommand(AbstractColtRunCommand):

        def run(self):
                settings = self.getSettings()                
                
                # TODO: detect if colt is running and skip running it if it is
                COLT.colt.runCOLT(settings)

class OpenInColtCommand(AbstractColtRunCommand):

        html = None

        def run(self):
                settings = self.getSettings()
                
                # Check the file name
                file = self.window.active_view().file_name()
                if re.match(r'.*\.html?$', file):
                    OpenInColtCommand.html = file
                    
                if OpenInColtCommand.html is None :
                    # Error message
                    sublime.error_message('This tab is not html file. Please open project main html and try again.')
                    return

                # Export COLT project
                coltProjectFilePath = COLT.colt.exportProject(self.window, OpenInColtCommand.html)

                # Add project to workset file
                COLT.colt.addToWorkingSet(coltProjectFilePath)

                # Run COLT
                COLT.colt_rpc.initAndConnect(settings, coltProjectFilePath)

                # Authorize
                COLT.colt_rpc.runAfterAuthorization = None
                COLT.colt_rpc.authorize(self.window)                                                          

class RunWithColtCommand(AbstractColtRunCommand):

        def run(self):
                settings = self.getSettings()
                
                # Check the file name
                file = self.window.active_view().file_name()
                if re.match(r'.*\.html?$', file):
                    OpenInColtCommand.html = file
                    
                if OpenInColtCommand.html is None :
                    # Error message
                    sublime.error_message('This tab is not html file. Please open project main html and try again.')
                    return

                # Export COLT project
                coltProjectFilePath = COLT.colt.exportProject(self.window, OpenInColtCommand.html)

                # Add project to workset file
                COLT.colt.addToWorkingSet(coltProjectFilePath)

                # Run COLT
                COLT.colt_rpc.initAndConnect(settings, coltProjectFilePath)

                # Authorize and start live
                COLT.colt_rpc.runAfterAuthorization = COLT.colt_rpc.startLive
                COLT.colt_rpc.authorize(self.window)                                                          
