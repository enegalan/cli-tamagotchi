class CliTamagotchi < Formula
  include Language::Python::Virtualenv

  desc "Terminal Tamagotchi virtual pet for the CLI"
  homepage "https://github.com/enegalan/cli-tamagotchi"
  url "https://files.pythonhosted.org/packages/3a/39/c6be51b5c14c98e18cf8d0bb2ab377a391c8bb0813ec06cc787135b9db18/cli_tamagotchi-1.0.0.tar.gz"
  sha256 "5c8143e751499d30254a9483026c7e64c373642c869c92d431402951dc844907"
  license "MIT"

  depends_on "python@3.12"

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/38/71/3b932df36c1a044d397a1f92d1cf91ee0a503d91e470cbd670aa66b07ed0/markdown-it-py-3.0.0.tar.gz"
    sha256 "e3f60a94fa066dc52ec76661e37c851cb232d92f9886b15cb560aaada2df8feb"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz"
    sha256 "6757cd03768053ff99f3039c1a36d6c0aa0b263438fcab17520b30a303a82b5f"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/b3/c6/f3b320c27991c46f43ee9d856302c70dc2d0fb2dba4842ff739d5f46b393/rich-14.3.3.tar.gz"
    sha256 "b8daa0b9e4eef54dd8cf7c86c03713f53241884e814f4e2f5fb342fe520f639b"
  end

  def install
    venv = virtualenv_create(libexec, "python3.12")
    %w[mdurl markdown-it-py pygments rich].each do |dependency_name|
      venv.pip_install resource(dependency_name)
    end
    venv.pip_install_and_link buildpath
  end

  test do
    assert_match "usage:", shell_output("#{bin}/tama --help")
  end
end
