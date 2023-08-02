#include<Windows.h>
#include<bits/stdc++.h>
using namespace std;
/*function:
	recognize them when enemys were spotted
*/
/*compile:
	g++ -Wl,--stack=998244353 -std=c++17 -O3 recognize_enemy.cpp -o recognize_enemy.exe
*/

struct Image{
	//Default index start with 0
	//For grey image
	int n,m;
	double Brightness;
	char Name[25];
	double a[128][128];
	void turn()
	{
		double sum=0;
		for(int i=0;i<n;i++)
			for(int j=0;j<m;j++){
				if(a[i][j]>Brightness/n/m*1.2)
					a[i][j]+=10;
				if(a[i][j]<Brightness/n/m*0.8)
					a[i][j]-=10;
				sum+=a[i][j];
			}
		for(int i=0;i<n;i++)
			for(int j=0;j<m;j++)
				a[i][j]/=sum;
	}
	void read(ifstream &fin,int ReadName=0){
		//fin is a ifstream type
		if(ReadName)
			fin>>Name;
		fin>>n>>m;
		int sum=0;
		//Image of size n rows and m columns
		//n * m
		for(int i=0;i<n;i++)
			for(int j=0;j<m;j++){
				fin>>a[i][j];
				sum+=a[i][j];
			}
		Brightness=sum;
		turn();

	}
}Tem[100],Tar[100];
set<string> S1,S2,S3,S4;
char *ROOT;
template<typename T1, typename T2>
bool in(const T1 &Object, const T2 &Container){
	return Container.find(Object)!=Container.end();
}
double CalcImageSimilarity(Image a,Image b){
	//Calculate The Similarity between two images with the same size
	//Return is a double,the large the more different
	//Return for images with different size is 0
	if(max(a.Brightness,b.Brightness)/min(a.Brightness,b.Brightness)>=3)return 1.0;
	if(a.n!=b.n||a.m!=b.m)
		return 0;
	int n=a.n,m=a.m;

	double res = 1000;
	for(int i=-1;i<=1;i++)
		for(int j=-1;j<=1;j++){
			double now=0;
			for(int pa1=0;pa1<n;pa1++)
				for(int pa2=0;pa2<m;pa2++){
					int pb1=pa1+i,pb2=pa2+j;
					if(!(pb1<n&&pb2<m&&pb1>=0&&pb2>=0))
						continue;
					now+=abs(1.0*a.a[pa1][pa2]-1.0*b.a[pb1][pb2]);
				}
			res=min(res,now);
		}
	return res;
}
string merge(char* a,const char* b){
	char ch[1000];
	strcpy(ch, a);
	strcat(ch, b);
	return ch;
}
void recognize(ifstream &ain)
{
	int TemplateCount,TargetCount;
	ifstream fin(merge(ROOT, "/TemplateData"));
	ofstream fout(merge(ROOT, "/res.out"));
	fin>>TemplateCount;
	for(int i=0;i<TemplateCount;i++)
		Tem[i].read(fin,1);
	ain>>TargetCount;
	//S1:CA,CL,CAV,CLT,CBG,BC
	//S2:CV,CVL,AV
	//S3:BB,BC
	//S4:CL,CVL
	for(int i=0;i<TargetCount;i++){
		Tar[i].read(ain,0);
		Image now=Tem[0];
		for(int j=1;j<TemplateCount;j++){
			Image Target=Tar[i],Tem1=now,Tem2=Tem[j];
			double s1,s2;
			if((in(Tem1.Name,S1)&&in(Tem2.Name,S1))||(in(Tem1.Name,S2)&&in(Tem2.Name,S2))||(in(Tem1.Name,S3)&&in(Tem2.Name,S3))||(in(Tem1.Name,S4)&&in(Tem2.Name,S4))){
				Target.m=Tem1.m=Tem2.m=16;
				if((in(Tem1.Name,S3)&&in(Tem2.Name,S3))||(in(Tem1.Name,S4)&&in(Tem2.Name,S4)))
					for(int i=0;i<16;i++)
						for(int j=0;j<16;j++){
							Target.a[i][j]=Target.a[i][j+16];
							Tem1.a[i][j]=Tem1.a[i][j+16];
							Tem2.a[i][j]=Tem2.a[i][j+16];
						}
			}
			s1=CalcImageSimilarity(Target,Tem1);
			s2=CalcImageSimilarity(Target,Tem2);
			if(s1>s2)
				now=Tem[j];
		}
		fout<<now.Name<<' ';
	}
	fout.close();
	fin.close();
}
signed main(int argc, char** args)
{
	//Args given in the tunnel,file "args.in"
	//The exe will be put in the tunnel
	//S1:CA,CL,CAV,CLT,CBG,BC
	//S2:CV,CVL,AV
	//S3:BB,BC
	//S4:CL,CVL
	ROOT = args[1];
	S1.insert("CA"),S1.insert("CL");S1.insert("CAV");S1.insert("CLT");S1.insert("CBG");S1.insert("BC");
	S2.insert("CV"),S2.insert("AV"),S2.insert("CVL");
	S3.insert("BB"),S3.insert("BC");
	S4.insert("CL"),S4.insert("CVL");


	ifstream ain(merge(ROOT, "/args.in"));
//	cout<<merge(ROOT, "/args.in")<<endl;
	string name;
	while(ain>>name)
	{
		if(name=="recognize")
		recognize(ain);
	}
	ain.close();
	return 0;
}
