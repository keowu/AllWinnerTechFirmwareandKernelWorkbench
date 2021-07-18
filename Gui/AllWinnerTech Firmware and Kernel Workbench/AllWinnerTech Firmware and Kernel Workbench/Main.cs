using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

/// <summary>
///  AllWinner Tech Firmware and Kernel Workbench
/// </summary>
namespace AllWinnerTech_Firmware_and_Kernel_Workbench
{
    /// <summary>
    ///     Main Class
    /// </summary>
    public partial class Main : Form
    {

        /// <summary>
        ///  Windows API FORM DESIGN
        /// </summary>
        public const int WM_NCLBUTTONDOWN = 0xA1;
        public const int HT_CAPTION = 0x2;

        [System.Runtime.InteropServices.DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
        [System.Runtime.InteropServices.DllImport("user32.dll")]
        public static extern bool ReleaseCapture();

        /// <summary>
        ///  Main Class Constructor
        /// </summary>
        public Main()
        {
            InitializeComponent();
        }

        /// <summary>
        ///     Move with mouse event
        /// </summary>
        /// <param name="sender">this class object</param>
        /// <param name="e">Mouse arguments</param>
        private void ptop_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                ReleaseCapture();
                SendMessage(Handle, WM_NCLBUTTONDOWN, HT_CAPTION, 0);
            }
        }

        /// <summary>
        ///     Call Python repack script
        /// </summary>
        void repackMe()
        {
            System.Diagnostics.Process process = new System.Diagnostics.Process();
            System.Diagnostics.ProcessStartInfo startInfo = new System.Diagnostics.ProcessStartInfo();
            startInfo.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
            startInfo.FileName = "python";
            startInfo.Arguments =  (this.btnP2.Checked ? "boot2.py" : "boot3.py") + " --repack-bootimg";
            process.StartInfo = startInfo;
            process.Start();

            if (btnFuckFEX.Checked && !this.changeBootName("boot.img", "boot.fex"))
            {
                MessageBox.Show("Não foi possível trabalhar com o boot.fex !");
                return;
            }
        }


        /// <summary>
        ///     Change boot fex name to img to work easy
        /// </summary>
        /// <param name="shitName">old name</param>
        /// <param name="shitNewName">new name</param>
        /// <returns>if all is nice</returns>
        bool changeBootName(String shitName, String shitNewName)
        {
            if (File.Exists(shitName))
            {
                File.Copy(shitName, shitNewName, true);
                File.Delete(shitName);
                return true;
            }
            return false;
        }

        /// <summary>
        ///     Call Python unpack script
        /// </summary>
        void unpackMe()
        {
            if (btnFuckFEX.Checked && !this.changeBootName("boot.fex", "boot.img"))
            {
                MessageBox.Show("Não foi possível trabalhar com o boot.fex !");
                return;
            }

            System.Diagnostics.Process process = new System.Diagnostics.Process();
            System.Diagnostics.ProcessStartInfo startInfo = new System.Diagnostics.ProcessStartInfo();
            startInfo.WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden;
            startInfo.FileName = "python";
            startInfo.Arguments = (this.btnP2.Checked ? "boot2.py" : "boot3.py") + " --unpack-bootimg " + (this.btnFuckFEX.Checked ? "boot.fex" : "boot.img") + "";
            process.StartInfo = startInfo;
            process.Start();
        }

        /// <summary>
        ///     Button unpack click event
        /// </summary>
        /// <param name="sender">This class object</param>
        /// <param name="e">Params for this event call</param>
        private void btnUnpack_Click(object sender, EventArgs e)
        {
            this.unpackMe();
        }

        /// <summary>
        ///     Button killme event
        /// </summary>
        /// <param name="sender">This class object</param>
        /// <param name="e">Params for this event call</param>
        private void btnKillMe_Click(object sender, EventArgs e)
        {
            this.Dispose();
        }

        /// <summary>
        ///     Button pack click event
        /// </summary>
        /// <param name="sender">This class object</param>
        /// <param name="e">Params for this event call</param>
        private void btnPack_Click(object sender, EventArgs e)
        {
            this.repackMe();
        }

        /// <summary>
        ///     BTN ABOUT DUDE, BTN ABOUT YEAHHHH !
        /// </summary>
        /// <param name="sender">This class object</param>
        /// <param name="e">Params for this event call</param>
        private void btnAbout_Click(object sender, EventArgs e)
        {
            MessageBox.Show("Dev by Keowu go to -> www.github.com/keowu");
            MessageBox.Show("Because we don't know how Operating Systems Work, and we break companies' career shit paths.");
            Process navegador = new Process();
            try
            {
                navegador.StartInfo.UseShellExecute = true;
                navegador.StartInfo.FileName = "http://www.github.com/keowu";
                navegador.Start();
            }
            catch (Exception) { }
        }
    }
}
