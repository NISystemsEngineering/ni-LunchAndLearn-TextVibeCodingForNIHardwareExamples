using System;
using System.Windows.Forms;

namespace NationalInstruments.Examples.VST5842Loopback
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}
