/*
	function:
		process decisive_battle map image for recognize
	parameters:
		Image absolute path
	compile command:
		g++ -o process_recognize_map process_recognize_map.cpp -I C:\Develop\opencv\opencv-4.5.4-mingw64\include -L C:\Develop\opencv\opencv-4.5.4-mingw64\lib -l libopencv_core454 -l libopencv_imgcodecs454
*/
#include "opencv2/opencv.hpp"
#include "module/image_function.h"

using namespace std;
using cv::Mat;
using cv::imread;
using cv::imwrite;
struct block{
	int left, right, top, bottom;
	void operator +=(const block &x){
			left=min(left, x.left);
			top=min(top, x.top);
			bottom=max(bottom, x.bottom);
			right=max(right, x.right);
	}
	bool operator ==(const block &x){
		return left == x.left && right == x.right && top == x.top && bottom == x.bottom;
	}
};
struct blocked_image{
	vector<vector<bool>> rec;
	vector<block> b, blocks;
	vector<int> fa;
	int row, col;
	int find_root(int x){
		return fa[x]==x?fa[x]:fa[x]=find_root(fa[x]);
	}
	void merge(int u,int v){
		u=find_root(u), v=find_root(v);
		if(u==v)return ;
		b[u]+=b[v], fa[v]=u;
	}
	int get_rk(int x, int y){
		return x * col + y;
	}
	void init(string image_path){
		Mat image = imread(image_path);
		row=image.rows, col=image.cols;
		rec.resize(row, vector<bool> (0)), blocks.clear();
		for(int i=0;i<row;i++){
			uchar* ptr=image.ptr<uchar>(i);
			for(int j=0;j<col;j++){
				const vector<vector<int>> COLOR_TEMPLATE({{225, 225, 225}});
				rec[i].push_back(is_key_color(ptr, COLOR_TEMPLATE, 50.0, 3));
				ptr+=3;
				// cout<<rec[i][j];
			}
			// cout<<'\n';
		}
		b.clear(), fa.clear();
		int size=row * col;
		rec.resize(size), fa.resize(size), b.resize(size);
		for(int i=0;i<row;i++){
			for(int j=0;j<col;j++){
				int rk=get_rk(i ,j);
				b[rk]=block{j, j, i, i};
				fa[rk]=rk;
				if(i&&rec[i-1][j]){
					merge(rk, get_rk(i - 1, j));
				}
				if(j&&rec[i][j-1]){
					merge(rk, get_rk(i, j - 1));
				}
			}
		}
		for(int i=0; i<size; i++)if(fa[i]==i&&b[i].left!=b[i].right){
			// cout<<i<<'\n';
			blocks.push_back(b[i]);
		}
	}
}img;
bool cmp(const block &a, const block &b){
	return a.top < b.top;
}
vector<int> scan_row_rev(const vector<vector<bool>> &x){
	int row=x.size(), col=x[0].size();
	vector<int> res(0);
	for(int i=0;i<row;i++){
		int exist=0, sum=0, closed=0;
		for(int j=0;j<col;j++){
			exist|=x[i][j];
			sum+=exist && !x[i][j];
			closed|=sum && x[i][j];
		}
		res.push_back(sum * closed);
	}
	return res;
}
vector<int> scan_col_rev(const vector<vector<bool>> &x){
	int row=x.size(), col=x[0].size();
	vector<int> res(0);
	for(int i=0;i<col;i++){
		int exist=0, sum=0, closed=0;
		for(int j=0;j<row;j++){
			exist|=x[j][i];
			sum+=exist && !x[j][i];
			closed|=sum && x[j][i];
		}
		res.push_back(sum * closed);
	}
	return res;
}
vector<int> scan_row(const vector<vector<bool>> &x){
	int row=x.size(), col=x[0].size();
	vector<int> res(0);
	for(int i=0;i<row;i++){
		int sum=0;
		for(int j=0;j<col;j++){
			sum+=x[i][j];
		}
		res.push_back(sum);
	}
	return res;
}
string replaceLastSegmentWith(const string& path, const string& new_segment) {
    // 查找最后一个路径分隔符（在Windows上是'\\'，在Unix/Linux上是'/'）
    size_t pos = path.find_last_of("/\\");

    // 如果找到了分隔符，替换最后一级
    if (pos != string::npos) {
        return path.substr(0, pos + 1) + new_segment;
    } else {
        // 如果没有找到分隔符，说明路径中没有子目录，直接返回新路径
        return new_segment;
    }
}
int main(int argc, char **args){

	freopen(replaceLastSegmentWith(args[1], "1.out").data(), "w", stdout);
	img.init(args[1]);
	sort(img.blocks.begin(), img.blocks.end(), cmp);
	Mat M(img.blocks[0].bottom - img.blocks[0].top + 1, img.blocks[0].right - img.blocks[0].left + 1, CV_8UC1);
	vector<vector<bool>> cropped_image;
	// cout << M.rows << ' ' << M.cols << '\n';
	// Mat M(img.blocks[0].right - img.blocks[0].left + 1, img.blocks[0].bottom - img.blocks[0].top + 1, CV_8UC1);
	for(int i=img.blocks[0].top; i<=img.blocks[0].bottom; i++){
		cropped_image.push_back(vector<bool> (0));
		for(int j=img.blocks[0].left; j<=img.blocks[0].right; j++){
			int rk=img.get_rk(i, j);
			int col = 230 * img.rec[i][j] * (img.b[img.find_root(rk)]==img.blocks[0]);
			cropped_image[i - img.blocks[0].top].push_back(col);
			M.at<uchar>(i - img.blocks[0].top, j - img.blocks[0].left)=col;
			if(bool(img.b[img.find_root(rk)]==img.blocks[0])){
				// cout<<'#';
			}
			else{
				// cout<<'.';
			}
		}
		// cout<<'\n';
	}
	// calculate interval length for rows and columns
	const int inv_count_limit = 2;
	auto line_col_rev = scan_col_rev(cropped_image);
	auto line_row_rev = scan_row_rev(cropped_image);
	auto line_row = scan_row(cropped_image);
	// cout<<"D:";for(auto x:line_col_rev)cout<<x<<" ";cout<<'\n';
	// cout<<"D:";for(auto x:line_row_rev)cout<<x<<" ";cout<<'\n';
	// cout<<"D:";for(auto x:line_row)cout<<x<<" ";cout<<'\n';

	auto row_inv_count=0, col_inv_count=0;
	for(auto x:line_col_rev)if(x){
		col_inv_count++;
	}
	for(auto x:line_row_rev)if(x){
		row_inv_count++;
	}

	// identify characters by interval lengths
	if(row_inv_count > inv_count_limit){
		if(col_inv_count > inv_count_limit){
			const int accepted_length_limit=2;
			int last=0, type=-1, seg_count=0, start_with=bool(line_row_rev[0]);
			for(auto x:line_row_rev){
				if(type==-1||bool(x)!=type){
					if(last >= accepted_length_limit){
						seg_count ++;
					}
					last=1, type=bool(x);
				}
				else{
					last ++;
				}
			}
			if(last >= accepted_length_limit){
				seg_count ++;
			}
			if(seg_count == 3){
				if(start_with == 0){
					cout<<'D'<<'\n';
				}
				else{
					cout<<'H'<<'\n';
				}
			}
			if(seg_count == 4){
				cout<<'A'<<'\n';
			}
			if(seg_count == 5){
				const int BC_col_inv_limit=15;
				if(col_inv_count > BC_col_inv_limit){
					cout<<'C'<<'\n';
				}
				else{
					cout<<'B'<<'\n';
				}
			}
			if(seg_count == 7){
				cout<<'G'<<'\n';
			}
		}
		else{
			cout<<'H'<<"\n";
		}
	}
	else{
		if(col_inv_count > inv_count_limit){
			int min_size=100, count=0;
			const int limit=18;
			for(auto x:line_row){
				if(x > 2)min_size=min(min_size, x);
			}
			for(auto x:line_row){
				if(x > 1.5 * min_size)count++;
			}
			// cerr<<"T:"<<min_size<<'\n';
			// cerr<<"T:"<<count<<'\n';
			if(count>=limit)cout<<'E'<<'\n';
			else cout<<'F'<<'\n';
		}
		else{
			const int length_diff_limit=3;
			int min_size=100, max_size=0;
			for(auto x:line_row)if(x > 2){
				min_size=min(min_size, x);
				max_size=max(max_size, x);
			}
			if(max_size - min_size > length_diff_limit){
				cout<<'J'<<'\n';
			}
			else{
				cout<<'I'<<'\n';
			}
		}
	}
	imwrite(string(args[1]), M);    //保存生成的图片
	return 0;
}
